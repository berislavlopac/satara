# List available recipes.
help:
    @just --list --unsorted

# Run all unit tests.
[group('Testing')]
test-all:
    uv run --all-groups pytest --spec

# Run all unit tests with coverage report.
[group('Testing')]
test-cov:
    uv run --all-groups pytest --spec --cov

# The suites are split by the service they need, so either can be run without
# standing up the other. Each fails rather than skips when its service is
# missing: a suite that skips everything reports success, which is the one
# outcome an integration run must never produce.
#
# Neither is measured for coverage. What they are worth is that a path works
# against real infrastructure, which a percentage does not express, and scoping
# the measurement to the modules they happen to touch meant a list that grew
# with every test and gated nothing. Coverage of the source tree is the unit
# suite's job, where the 80% floor is enforced.

# Run integration tests.
[group('Testing')]
test-integration:
    echo "Not implemented."

# Run linting and formating checks.
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

# Run basic code and audit checks.
[group('Development')]
check-audit: lint type

# Reformat the code using isort and ruff.
[group('Development')]
[confirm]
reformat:
    uv run ruff format .
    uv run ruff check --select I --fix .

# Install git hooks (pre-commit, post-checkout, post-merge auto-sync).
[group('Development')]
install-hooks:
    uv run pre-commit install

# Serve the documentation site locally.
[group('Documentation')]
docs:
    uv run mkdocs serve --livereload -a localhost:7000

# Extract current production requirements. Save to a file by appending `> requirements.txt`.
[group('Tools')]
reqs:
    uv export --format requirements-txt --no-dev

