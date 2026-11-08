default:
    @just --list

# Set up the project environment and install development tools.
sync:
    uv sync

# Run Ruff lint checks.
lint:
    uv run ruff check

# Lint the Ansible deployment (requires ansible-lint on PATH).
lint-ansible:
    ansible-lint ansible/site.yaml

# Build the current wheel, then deploy it using the local Ansible inventory.
deploy *args: build
    ansible-playbook -i ansible/inventory.yaml ansible/site.yaml {{ args }}

# Format the project with Ruff.
format:
    uv run ruff format

# Check formatting without modifying files.
format-check:
    uv run ruff format --check

# Run the test suite with pytest.
test:
    uv run pytest

# Run ty's static type checker.
typecheck:
    uv run ty check

# Run lint, formatting, type checking, and tests.
check: lint format-check typecheck test

# Build source and wheel distributions.
build:
    uv build

# Remove generated project artifacts.
clean:
    rm -rf .venv .ruff_cache dist build
