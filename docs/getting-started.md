# Getting started

## Run it with Docker

With [just](https://just.systems):

```shell
just build-image
just run-image
```

Or with Docker alone:

```shell
docker build -t satara .
docker run --rm -p 8000:8000 satara
```

The service listens on <http://localhost:8000>. Try it with:

```shell
curl --form files=@notes.txt --form files=@data.csv --form name=report \
    --output report.zip http://localhost:8000/archive-files
```

Interactive API documentation is served at <http://localhost:8000/docs>.

## Set it up for development

The project uses [uv](https://docs.astral.sh/uv/) for its environment and dependencies. uv
installs the Python version the project needs, 3.14, if it is not already present.

```shell
uv sync --all-groups
uv run prek install
```

The first command installs every dependency group, including the development tools; the
second installs the Git hooks, which check each commit before it is made.

Tasks are run through `just` recipes. `just` is one of the development dependencies, so
`uv run just <recipe>` works without installing it separately; with `just` installed, the
`uv run` prefix can be dropped.

| Recipe        | What it does                                                    |
|---------------|-----------------------------------------------------------------|
| `serve`       | Serve the API locally, reloading on code changes.               |
| `test`        | Run the unit tests.                                             |
| `test-cov`    | Run the unit tests with a coverage report and the 85% floor.    |
| `check`       | Run the lint, formatting, dependency and type checks.           |
| `reformat`    | Reformat the code and sort the imports.                         |
| `docs`        | Serve this documentation locally, reloading on changes.         |
| `build-docs`  | Build this documentation, failing on any warning.               |
| `build-image` | Build the Docker image.                                         |
| `run-image`   | Run the Docker image, serving on port 8000.                     |

`just --list` shows them all.
