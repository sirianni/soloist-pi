"""Offline tests for the Soloist updater and archive validation."""

from __future__ import annotations

import gzip
import io
import json
import os
import stat
import tarfile
import threading
from collections.abc import Callable
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx
import pytest
import respx

from soloist_pi import updater
from soloist_pi.updater import ReleaseMetadata, UpdateError, update_binary


def make_executable(
    version: str = "soloist 1.2.3", *, exit_status: int = 0, output: str | None = None
) -> bytes:
    version_output = output if output is not None else version
    return (
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f"  printf '%s\\n' {version_output!r}\n"
        f"  exit {exit_status}\n"
        "fi\n"
        "exit 0\n"
    ).encode()


def make_archive(
    members: list[tuple[str, bytes, str | None]] | None = None,
) -> bytes:
    if members is None:
        members = [("soloist", make_executable(), None)]
    tar_bytes = io.BytesIO()
    with tarfile.open(fileobj=tar_bytes, mode="w:") as archive:
        for name, body, linkname in members:
            info = tarfile.TarInfo(name)
            if linkname is None:
                info.size = len(body)
                archive.addfile(info, io.BytesIO(body))
            else:
                info.type = tarfile.SYMTYPE
                info.linkname = linkname
                archive.addfile(info)
    return gzip.compress(tar_bytes.getvalue())


MOCK_CDN_URL = "https://cdn.example.test/soloist.tar.gz"


class MockCDN:
    def __init__(
        self,
        router: respx.Router,
        *,
        body: bytes | None = None,
        etag: str | None = '"release-1"',
        last_modified: str | None = "Wed, 01 Jan 2025 00:00:00 GMT",
        status: int = 200,
    ) -> None:
        self.url = MOCK_CDN_URL
        self.body = body if body is not None else make_archive()
        self.etag = etag
        self.last_modified = last_modified
        self.status = status
        self.requests: list[str] = []
        self.user_agents: list[str | None] = []
        self.head_route = router.head(self.url).mock(side_effect=self._head)
        self.get_route = router.get(self.url).mock(side_effect=self._get)

    def _head(self, request: httpx.Request) -> httpx.Response:
        return self._respond(request, method="HEAD")

    def _get(self, request: httpx.Request) -> httpx.Response:
        return self._respond(request, method="GET")

    def _respond(self, request: httpx.Request, *, method: str) -> httpx.Response:
        self.requests.append(method)
        self.user_agents.append(request.headers.get("User-Agent"))
        headers = {"Content-Length": str(len(self.body))}
        if self.etag is not None:
            headers["ETag"] = self.etag
        if self.last_modified is not None:
            headers["Last-Modified"] = self.last_modified
        body = self.body if method == "GET" and self.status == 200 else b""
        return httpx.Response(
            self.status,
            headers=headers,
            content=body,
            request=request,
        )


class TruncatedCDN:
    def __init__(self, body: bytes) -> None:
        cdn = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                self.send_response(200)
                self.send_header("Content-Length", str(len(cdn.body) + 10))
                self.end_headers()
                self.wfile.write(cdn.body)

            def log_message(self, format: str, *args: object) -> None:
                del format, args

        self.body = body
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/soloist.tar.gz"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback
        self.close()


def paths(tmp_path: Path) -> tuple[Path, Path]:
    managed_dir = tmp_path / "bin"
    managed_dir.mkdir(mode=0o700)
    return managed_dir / "soloist", tmp_path / "release.json"


def test_download_installs_validated_executable_and_metadata(tmp_path: Path) -> None:
    binary, metadata = paths(tmp_path)
    with respx.mock(assert_all_called=False) as router:
        cdn = MockCDN(router)
        changed = update_binary(
            binary_path=binary,
            metadata_path=metadata,
            release_url=cdn.url,
        )

        assert changed is True
        assert binary.read_bytes() == make_executable()
        assert stat.S_IMODE(binary.stat().st_mode) == 0o755
        saved = json.loads(metadata.read_text(encoding="utf-8"))
        assert saved["etag"] == '"release-1"'
        assert stat.S_IMODE(metadata.stat().st_mode) == 0o600
        assert cdn.requests == ["HEAD", "GET"]
        assert cdn.user_agents == [updater.USER_AGENT, updater.USER_AGENT]

        assert (
            update_binary(
                binary_path=binary,
                metadata_path=metadata,
                release_url=cdn.url,
            )
            is False
        )
        assert cdn.requests == ["HEAD", "GET", "HEAD"]


def test_forced_update_skips_head_and_downloads_unchanged_release(
    tmp_path: Path,
) -> None:
    binary, metadata = paths(tmp_path)
    with respx.mock(assert_all_called=False) as router:
        cdn = MockCDN(router)
        update_binary(binary_path=binary, metadata_path=metadata, release_url=cdn.url)
        cdn.requests.clear()

        assert (
            update_binary(
                binary_path=binary,
                metadata_path=metadata,
                release_url=cdn.url,
                force=True,
            )
            is True
        )
        assert cdn.requests == ["GET"]


def test_changed_etag_downloads_new_binary(tmp_path: Path) -> None:
    binary, metadata = paths(tmp_path)
    with respx.mock(assert_all_called=False) as router:
        cdn = MockCDN(router)
        update_binary(binary_path=binary, metadata_path=metadata, release_url=cdn.url)
        cdn.etag = '"release-2"'
        cdn.body = make_archive([("soloist", make_executable("soloist 2.0"), None)])

        assert (
            update_binary(
                binary_path=binary,
                metadata_path=metadata,
                release_url=cdn.url,
            )
            is True
        )
        assert binary.read_bytes() == make_executable("soloist 2.0")
        assert cdn.requests[-2:] == ["HEAD", "GET"]


def test_validator_comparison_precedence_and_fallbacks() -> None:
    baseline = ReleaseMetadata(
        url="https://example.invalid/soloist.tar.gz",
        etag="one",
        checksum_crc32c="crc-a",
        last_modified="Wed, 01 Jan 2025 00:00:00 GMT",
        content_length=100,
    )
    assert updater._same_release(baseline, baseline)
    assert not updater._same_release(replace(baseline, etag="two"), baseline)

    etag_missing = ReleaseMetadata(
        url=baseline.url,
        checksum_crc32c="crc-a",
        last_modified=baseline.last_modified,
        content_length=100,
    )
    assert updater._same_release(etag_missing, etag_missing)
    assert not updater._same_release(
        replace(etag_missing, checksum_crc32c="crc-b"),
        etag_missing,
    )

    no_checksum = ReleaseMetadata(
        url=baseline.url,
        last_modified=baseline.last_modified,
        content_length=100,
    )
    assert updater._same_release(no_checksum, no_checksum)
    assert not updater._same_release(
        replace(no_checksum, content_length=101),
        no_checksum,
    )
    assert not updater._same_release(
        ReleaseMetadata(url=baseline.url), ReleaseMetadata(url=baseline.url)
    )


@pytest.mark.parametrize(
    "members",
    [
        [("./soloist", make_executable(), None)],
        [("../soloist", make_executable(), None)],
        [("elsewhere/soloist", make_executable(), None)],
        [("soloist", b"", "target")],
        [("soloist", b"", None), ("other", b"x", None)],
        [("soloist", b"", None), ("soloist", b"", None)],
    ],
    ids=["dot-alias", "traversal", "nested", "symlink", "extra-member", "duplicate"],
)
def test_rejects_unsafe_or_ambiguous_archives_and_preserves_binary(
    tmp_path: Path, members: list[tuple[str, bytes, str | None]]
) -> None:
    binary, metadata = paths(tmp_path)
    previous = make_executable("soloist 0.9")
    binary.write_bytes(previous)
    binary.chmod(0o755)
    with respx.mock(assert_all_called=False) as router, pytest.raises(UpdateError):
        cdn = MockCDN(router, body=make_archive(members))
        update_binary(
            binary_path=binary,
            metadata_path=metadata,
            release_url=cdn.url,
            force=True,
        )
    assert binary.read_bytes() == previous
    assert stat.S_IMODE(binary.stat().st_mode) == 0o755
    assert not metadata.exists()


def test_invalid_staged_binary_preserves_existing_install(tmp_path: Path) -> None:
    binary, metadata = paths(tmp_path)
    previous = make_executable("soloist 0.9")
    binary.write_bytes(previous)
    binary.chmod(0o755)
    invalid = b"#!/bin/sh\nprintf 'not soloist\\n'\n"
    with (
        respx.mock(assert_all_called=False) as router,
        pytest.raises(UpdateError, match="failed --version"),
    ):
        cdn = MockCDN(router, body=make_archive([("soloist", invalid, None)]))
        update_binary(
            binary_path=binary,
            metadata_path=metadata,
            release_url=cdn.url,
            force=True,
        )
    assert binary.read_bytes() == previous
    assert not metadata.exists()


def test_failed_metadata_commit_rolls_back_binary(
    tmp_path: Path, monkeypatch: Any
) -> None:
    binary, metadata = paths(tmp_path)
    previous = make_executable("soloist 0.9")
    binary.write_bytes(previous)
    binary.chmod(0o755)
    original_replace: Callable[..., None] = os.replace

    def replace(source: Any, destination: Any) -> None:
        if Path(destination) == metadata:
            raise OSError("simulated metadata failure")
        original_replace(source, destination)

    monkeypatch.setattr(updater.os, "replace", replace)
    with (
        respx.mock(assert_all_called=False) as router,
        pytest.raises(UpdateError, match="cannot commit"),
    ):
        cdn = MockCDN(router)
        update_binary(
            binary_path=binary,
            metadata_path=metadata,
            release_url=cdn.url,
            force=True,
        )
    assert binary.read_bytes() == previous
    assert not metadata.exists()


def test_oversized_archive_is_rejected_before_install(
    tmp_path: Path, monkeypatch: Any
) -> None:
    binary, metadata = paths(tmp_path)
    monkeypatch.setattr(updater, "MAX_ARCHIVE_BYTES", 100)
    with (
        respx.mock(assert_all_called=False) as router,
        pytest.raises(UpdateError, match="size limit"),
    ):
        cdn = MockCDN(router, body=b"x" * 101)
        update_binary(
            binary_path=binary,
            metadata_path=metadata,
            release_url=cdn.url,
            force=True,
        )
    assert not binary.exists()


def test_unavailable_cdn_does_not_modify_a_usable_install(tmp_path: Path) -> None:
    binary, metadata = paths(tmp_path)
    previous = make_executable("soloist 0.9")
    binary.write_bytes(previous)
    binary.chmod(0o755)

    def fail_to_connect(request: httpx.Request) -> None:
        raise httpx.ConnectError("offline", request=request)

    with respx.mock(assert_all_called=False) as router:
        router.head(MOCK_CDN_URL).mock(side_effect=fail_to_connect)
        with pytest.raises(UpdateError, match="release metadata failed"):
            update_binary(
                binary_path=binary,
                metadata_path=metadata,
                release_url=MOCK_CDN_URL,
            )

    assert updater.is_usable_binary(binary)
    assert binary.read_bytes() == previous


def test_rejects_non_200_and_truncated_download(tmp_path: Path) -> None:
    binary, metadata = paths(tmp_path)
    with (
        respx.mock(assert_all_called=False) as router,
        pytest.raises(UpdateError, match="HTTP 503"),
    ):
        cdn = MockCDN(router, status=503)
        update_binary(
            binary_path=binary,
            metadata_path=metadata,
            release_url=cdn.url,
        )

    previous = make_executable("soloist 0.9")
    binary.write_bytes(previous)
    binary.chmod(0o755)
    with TruncatedCDN(make_archive()) as cdn, pytest.raises(UpdateError):
        update_binary(
            binary_path=binary,
            metadata_path=metadata,
            release_url=cdn.url,
            force=True,
        )
    assert binary.read_bytes() == previous
    assert updater.is_usable_binary(binary)
    assert not metadata.exists()
