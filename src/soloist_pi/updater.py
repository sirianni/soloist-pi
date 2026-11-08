"""Download, validate, and atomically install the managed Soloist executable."""

from __future__ import annotations

import gzip
import http.client
import json
import os
import selectors
import signal
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO

DEFAULT_RELEASE_URL = (
    "https://soloist-builds.spotifycdn.com/soloist_release_arm64.tar.gz"
)
DEFAULT_BINARY_PATH = Path("/var/lib/soloist/bin/soloist")
DEFAULT_METADATA_PATH = Path("/var/lib/soloist/bin/release.json")
USER_AGENT = "soloist-pi"

HEAD_TIMEOUT_SECONDS = 30
DOWNLOAD_TIMEOUT_SECONDS = 300
VERSION_TIMEOUT_SECONDS = 15
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
MAX_DECOMPRESSED_ARCHIVE_BYTES = MAX_EXECUTABLE_BYTES + 1024 * 1024
MAX_VERSION_OUTPUT_BYTES = 4096
_CHUNK_SIZE = 64 * 1024


class UpdateError(RuntimeError):
    """Raised when the current Soloist release cannot be installed safely."""


@dataclass(frozen=True)
class ReleaseMetadata:
    """Validators returned by the Soloist CDN for its stable archive."""

    url: str
    etag: str | None = None
    checksum_crc32c: str | None = None
    last_modified: str | None = None
    content_length: int | None = None

    @classmethod
    def from_headers(cls, url: str, headers: object) -> ReleaseMetadata:
        """Build metadata from an HTTP response's headers."""
        etag = _header(headers, "ETag")
        checksum = _header(headers, "X-Amz-Checksum-Crc32c")
        last_modified = _header(headers, "Last-Modified")
        length_value = _header(headers, "Content-Length")
        content_length: int | None = None
        if length_value is not None:
            try:
                content_length = int(length_value)
            except ValueError as exc:
                raise UpdateError("CDN returned an invalid Content-Length") from exc
            if content_length < 0:
                raise UpdateError("CDN returned an invalid Content-Length")
        for name, value in (
            ("ETag", etag),
            ("checksum", checksum),
            ("Last-Modified", last_modified),
        ):
            if value is not None and len(value) > 1024:
                raise UpdateError(f"CDN returned an overlong {name} header")
        return cls(
            url=url,
            etag=etag,
            checksum_crc32c=checksum,
            last_modified=last_modified,
            content_length=content_length,
        )


def update_binary(
    *,
    binary_path: Path | str = DEFAULT_BINARY_PATH,
    metadata_path: Path | str = DEFAULT_METADATA_PATH,
    release_url: str = DEFAULT_RELEASE_URL,
    force: bool = False,
) -> bool:
    """Ensure the managed binary is current; return whether it was replaced.

    A forced refresh skips the metadata probe and always downloads the archive.
    Network and archive failures leave an existing executable untouched.
    """
    target = Path(binary_path)
    metadata_file = Path(metadata_path)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    if not force:
        remote_metadata = _head_metadata(release_url)
        installed_version = _usable_version(target)
        saved_metadata = _load_metadata(metadata_file)
        if (
            installed_version is not None
            and saved_metadata is not None
            and _same_release(remote_metadata, saved_metadata)
        ):
            return False

    _download_and_install(
        release_url=release_url,
        binary_path=target,
        metadata_path=metadata_file,
    )
    return True


def is_usable_binary(path: Path | str = DEFAULT_BINARY_PATH) -> bool:
    """Return whether a managed regular executable passes its version probe."""
    return _usable_version(Path(path)) is not None


def binary_version(path: Path | str = DEFAULT_BINARY_PATH) -> str | None:
    """Return the validated version line, or ``None`` if the binary is unusable."""
    return _usable_version(Path(path))


def _head_metadata(url: str) -> ReleaseMetadata:
    request = urllib.request.Request(
        url,
        method="HEAD",
        headers={"User-Agent": USER_AGENT},
    )
    response = _open_request(request, HEAD_TIMEOUT_SECONDS, "release metadata")
    try:
        _require_success(response, "release metadata")
        _check_redirect_scheme(url, response.geturl())
        metadata = ReleaseMetadata.from_headers(url, response.headers)
        if (
            metadata.content_length is not None
            and metadata.content_length > MAX_ARCHIVE_BYTES
        ):
            raise UpdateError("Soloist archive exceeds the download size limit")
        return metadata
    finally:
        response.close()


def _download_and_install(
    *, release_url: str, binary_path: Path, metadata_path: Path
) -> None:
    binary_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    metadata_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    request = urllib.request.Request(
        release_url,
        method="GET",
        headers={"User-Agent": USER_AGENT},
    )
    response = _open_request(request, DOWNLOAD_TIMEOUT_SECONDS, "archive download")
    try:
        _require_success(response, "archive download")
        _check_redirect_scheme(release_url, response.geturl())
        downloaded_metadata = ReleaseMetadata.from_headers(
            release_url, response.headers
        )
        if (
            downloaded_metadata.content_length is not None
            and downloaded_metadata.content_length > MAX_ARCHIVE_BYTES
        ):
            raise UpdateError("Soloist archive exceeds the download size limit")

        with tempfile.TemporaryDirectory(
            prefix=".soloist-update-", dir=binary_path.parent
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)
            archive_path = temporary_path / "release.tar.gz"
            _copy_limited(response, archive_path)
            if (
                downloaded_metadata.content_length is not None
                and archive_path.stat().st_size != downloaded_metadata.content_length
            ):
                raise UpdateError("Soloist archive download was truncated")

            uncompressed_path = temporary_path / "release.tar"
            _decompress_limited(archive_path, uncompressed_path)
            staged_binary = temporary_path / "soloist"
            _extract_expected_executable(uncompressed_path, staged_binary)
            os.chmod(staged_binary, 0o755)
            _fsync_file(staged_binary)
            version = _usable_version(staged_binary)
            if version is None:
                raise UpdateError("downloaded Soloist executable failed --version")

            _commit_install(
                staged_binary=staged_binary,
                binary_path=binary_path,
                metadata_path=metadata_path,
                metadata=downloaded_metadata,
            )
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError(f"cannot install Soloist: {exc}") from exc
    finally:
        response.close()


def _copy_limited(response: object, destination: Path) -> None:
    total = 0
    try:
        with destination.open("xb") as output:
            while True:
                chunk = response.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ARCHIVE_BYTES:
                    raise UpdateError("Soloist archive exceeds the download size limit")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except UpdateError:
        raise
    except (OSError, http.client.HTTPException, urllib.error.URLError) as exc:
        raise UpdateError(f"cannot save Soloist archive: {exc}") from exc
    if total == 0:
        raise UpdateError("CDN returned an empty Soloist archive")


def _decompress_limited(source: Path, destination: Path) -> None:
    total = 0
    try:
        with (
            source.open("rb") as compressed,
            gzip.GzipFile(fileobj=compressed, mode="rb") as archive,
            destination.open("xb") as output,
        ):
            while True:
                chunk = archive.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_DECOMPRESSED_ARCHIVE_BYTES:
                    raise UpdateError(
                        "decompressed Soloist archive exceeds the size limit"
                    )
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    except UpdateError:
        raise
    except (OSError, EOFError, zlib.error) as exc:
        raise UpdateError(f"invalid gzip Soloist archive: {exc}") from exc


def _extract_expected_executable(archive_path: Path, destination: Path) -> None:
    try:
        with archive_path.open("rb") as stream:
            archive_size = archive_path.stat().st_size
            with tarfile.open(fileobj=stream, mode="r:") as archive:
                member = archive.next()
                if member is None:
                    raise UpdateError("Soloist archive is empty")
                if archive.next() is not None:
                    raise UpdateError(
                        "Soloist archive must contain exactly one member named 'soloist'"
                    )
                if member.name != "soloist":
                    raise UpdateError(
                        "Soloist archive member must be named exactly 'soloist'"
                    )
                if member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE):
                    raise UpdateError("Soloist archive member must be a regular file")
                if member.pax_headers:
                    raise UpdateError("Soloist archive must not use PAX extensions")
                if not 1 <= member.size <= MAX_EXECUTABLE_BYTES:
                    raise UpdateError(
                        "Soloist executable has an invalid or excessive size"
                    )
                source = archive.extractfile(member)
                if source is None:
                    raise UpdateError("cannot read Soloist archive member")
                copied = 0
                with source, destination.open("xb") as output:
                    while True:
                        chunk = source.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        copied += len(chunk)
                        if copied > MAX_EXECUTABLE_BYTES:
                            raise UpdateError(
                                "Soloist executable exceeds the size limit"
                            )
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if copied != member.size:
                    raise UpdateError("Soloist archive member was truncated")
                _verify_tar_padding(stream, archive.offset, archive_size)
    except UpdateError:
        raise
    except (OSError, tarfile.TarError, EOFError) as exc:
        raise UpdateError(f"invalid Soloist tar archive: {exc}") from exc


def _verify_tar_padding(stream: BinaryIO, offset: int, archive_size: int) -> None:
    if offset < 0 or offset + 1024 > archive_size:
        raise UpdateError("Soloist tar archive is missing its end-of-archive blocks")
    stream.seek(offset)
    while True:
        chunk = stream.read(_CHUNK_SIZE)
        if not chunk:
            break
        if any(chunk):
            raise UpdateError("unexpected data after Soloist tar archive")


def _commit_install(
    *,
    staged_binary: Path,
    binary_path: Path,
    metadata_path: Path,
    metadata: ReleaseMetadata,
) -> None:
    """Atomically replace binary and metadata, rolling back on commit failure."""
    metadata_temp: Path | None = None
    backup_path: Path | None = None
    had_binary = binary_path.exists()
    try:
        metadata_temp = _write_metadata_temp(metadata_path, metadata)
        if had_binary:
            backup_path = staged_binary.parent / "previous-soloist"
            os.link(binary_path, backup_path, follow_symlinks=False)
        os.replace(staged_binary, binary_path)
        try:
            os.replace(metadata_temp, metadata_path)
            metadata_temp = None
        except OSError:
            if backup_path is not None:
                os.replace(backup_path, binary_path)
                backup_path = None
            else:
                binary_path.unlink(missing_ok=True)
            raise
        _fsync_directory(binary_path.parent)
        if metadata_path.parent != binary_path.parent:
            _fsync_directory(metadata_path.parent)
    except UpdateError:
        raise
    except OSError as exc:
        raise UpdateError(f"cannot commit Soloist update: {exc}") from exc
    finally:
        if metadata_temp is not None:
            metadata_temp.unlink(missing_ok=True)
        if backup_path is not None:
            backup_path.unlink(missing_ok=True)


def _write_metadata_temp(metadata_path: Path, metadata: ReleaseMetadata) -> Path:
    payload = {"schema": 1, **asdict(metadata)}
    encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(
        prefix=f".{metadata_path.name}.", suffix=".tmp", dir=metadata_path.parent
    )
    temporary_path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as output:
            descriptor = -1
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        return temporary_path
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)
        raise UpdateError(f"cannot prepare Soloist release metadata: {exc}") from exc


def _load_metadata(path: Path) -> ReleaseMetadata | None:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None
    except OSError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024:
            return None
        with os.fdopen(descriptor, "rb") as source:
            descriptor = -1
            document = json.load(source)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(document, dict) or document.get("schema") != 1:
        return None
    url = document.get("url")
    if not isinstance(url, str):
        return None
    fields: dict[str, str | int | None] = {}
    for name in ("etag", "checksum_crc32c", "last_modified"):
        value = document.get(name)
        if value is not None and not isinstance(value, str):
            return None
        fields[name] = value
    content_length = document.get("content_length")
    if content_length is not None and (
        isinstance(content_length, bool)
        or not isinstance(content_length, int)
        or content_length < 0
    ):
        return None
    fields["content_length"] = content_length
    try:
        return ReleaseMetadata(url=url, **fields)  # type: ignore[arg-type]
    except TypeError:
        return None


def _same_release(remote: ReleaseMetadata, saved: ReleaseMetadata) -> bool:
    if remote.url != saved.url:
        return False
    if remote.etag is not None and saved.etag is not None:
        return remote.etag == saved.etag
    if remote.checksum_crc32c is not None and saved.checksum_crc32c is not None:
        return remote.checksum_crc32c == saved.checksum_crc32c
    if remote.last_modified is not None and saved.last_modified is not None:
        return (
            remote.last_modified == saved.last_modified
            and remote.content_length is not None
            and remote.content_length == saved.content_length
        )
    return False


def _usable_version(path: Path) -> str | None:
    try:
        info = path.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or not info.st_mode & 0o111:
        return None
    try:
        process = subprocess.Popen(
            [str(path), "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError:
        return None
    assert process.stdout is not None
    output = bytearray()
    deadline = time.monotonic() + VERSION_TIMEOUT_SECONDS
    selector = selectors.DefaultSelector()
    try:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _kill_version_process(process)
                return None
            if not selector.select(remaining):
                continue
            chunk = os.read(process.stdout.fileno(), 1024)
            if not chunk:
                selector.unregister(process.stdout)
                break
            output.extend(chunk)
            if len(output) > MAX_VERSION_OUTPUT_BYTES:
                _kill_version_process(process)
                return None
        try:
            status = process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            _kill_version_process(process)
            return None
        if status != 0:
            return None
    finally:
        selector.close()
        process.stdout.close()
    decoded = output.decode("utf-8", errors="replace")
    if not decoded.startswith("soloist "):
        return None
    return decoded.splitlines()[0].strip()


def _kill_version_process(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def _open_request(
    request: urllib.request.Request, timeout: int, description: str
) -> object:
    try:
        return urllib.request.urlopen(request, timeout=timeout)
    except (
        OSError,
        ValueError,
        urllib.error.URLError,
        urllib.error.HTTPError,
    ) as exc:
        if isinstance(exc, urllib.error.HTTPError):
            exc.close()
            message = f"HTTP {exc.code}"
        else:
            reason = getattr(exc, "reason", None)
            message = str(reason or exc)
        raise UpdateError(f"{description} failed: {message}") from exc


def _require_success(response: object, description: str) -> None:
    status = response.getcode()
    if status != 200:
        raise UpdateError(f"{description} returned HTTP {status}")


def _check_redirect_scheme(original_url: str, final_url: str) -> None:
    original_scheme = urllib.parse.urlsplit(original_url).scheme.lower()
    final_scheme = urllib.parse.urlsplit(final_url).scheme.lower()
    if original_scheme != final_scheme:
        raise UpdateError("CDN redirect changed the URL scheme")


def _header(headers: object, name: str) -> str | None:
    value = headers.get(name)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    """Best-effort durability for a completed same-directory rename."""
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
