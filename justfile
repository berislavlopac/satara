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
    uv run ruff format --check --output-format concise .
    uv run ruff check --output-format concise .

# Run static typing analysis.
[group('Development')]
type:
    uv run --all-groups pyrefly check --output-format min-text

# Run basic code and type checks.
[group('Development')]
check: lint type

# Reformat the code and sort the imports.
[group('Development')]
[confirm]
reformat:
    uv run ruff format .
    uv run ruff check --select I --fix .

# Extract current production requirements. Save to a file by appending `> requirements.txt`.
[group('Tools')]
reqs:
    uv export --format requirements-txt --no-default-groups
