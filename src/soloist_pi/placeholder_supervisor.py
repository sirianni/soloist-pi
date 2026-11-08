"""Run the built-in placeholder through the process supervisor."""

from soloist_pi.supervisor import run_placeholder


def main() -> int:
    """Start the placeholder child and supervise its shutdown."""
    return run_placeholder()


if __name__ == "__main__":
    raise SystemExit(main())
