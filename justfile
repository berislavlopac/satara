# Output formats for the checkers, overridable from the environment: CI sets both to
# `github`, so each error is annotated on its line in the pull request.
ruff_format := env("RUFF_OUTPUT_FORMAT", "concise")
pyrefly_format := env("PYREFLY_OUTPUT_FORMAT", "min-text")

# List available recipes.
help:
    @just --list --unsorted

# Run the unit tests.
[group('Testing')]
test:
    uv run --all-groups pytest --spec

# Run the unit tests with a coverage report.
[group('Testing')]
test-cov:
    uv run --all-groups pytest --spec --cov

# Serve the API locally, reloading on code changes.
[group('Development')]
serve:
    uv run uvicorn --factory satara.wiring:create_app --reload

# Run linting and formatting checks.
[group('Development')]
lint:
    uv run --all-groups deptry .
    uv run ruff format --check --output-format {{ ruff_format }} .
    uv run ruff check --output-format {{ ruff_format }} .

# Run static typing analysis.
[group('Development')]
type:
    uv run --all-groups pyrefly check --output-format {{ pyrefly_format }}

# Run basic code and type checks.
[group('Development')]
check: lint type

# Reformat the code and sort the imports.
[group('Development')]
[confirm]
reformat:
    uv run ruff format .
    uv run ruff check --select I --fix .

# Build the Docker image.
[group('Docker')]
build-image:
    docker build -t satara .

# Run the Docker image, serving on port 8000.
[group('Docker')]
run-image:
    docker run --rm -p 8000:8000 satara

# Extract current production requirements. Save to a file by appending `> requirements.txt`.
[group('Tools')]
reqs:
    uv export --format requirements-txt --no-default-groups
