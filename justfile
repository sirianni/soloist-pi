default:
    @just --list

# Set up the project environment and install development tools.
sync:
    uv sync

# Run Ruff lint checks.
lint:
    uv run ruff check .

# Format the project with Ruff.
format:
    uv run ruff format .

# Check formatting without modifying files.
format-check:
    uv run ruff format --check .

# Run the unit tests.
test:
    uv run python -m unittest discover -s tests

# Run lint, formatting, and tests.
check: lint format-check test

# Build source and wheel distributions.
build:
    uv build

# Install or replace the user-local isolated uv tool environment.
install:
    uv tool install --force .

# Remove generated project artifacts.
clean:
    rm -rf .venv .ruff_cache dist build
