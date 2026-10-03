# Getting started

Running the service needs [Docker](https://docs.docker.com/get-docker/). The `just` recipes below also need [uv](https://docs.astral.sh/uv/), which brings `just` with the project's development tools: run them as `uv run just <recipe>`, or drop the `uv run` with `just` installed.

## Run the service on its own

One container serves the direct flow, with nothing else needed:

```shell
just build-image
just run-image
```

Or with Docker alone:

```shell
docker build -t satara .
docker run --rm -p 8000:8000 satara
```

The service listens on <http://localhost:8000>, and documents its own API at <http://localhost:8000/docs>.

## Run the whole stack

The deferred flow needs storage and a queue consumer as well. Docker Compose runs them all, with MiniStack, an emulator, standing in for S3 and SQS:

```shell
just up
```

This builds the image and starts the service, with the deferred flow switched on, the consumer, the emulator, and a step that creates the bucket and the queues, then waits until all are healthy. The service is at <http://localhost:8000> and storage at <http://localhost:4566>. `just down` stops it all.

## Try it

With the service running, archive some files in one request:

```shell
just archive notes.txt data.csv --name report
```

With the whole stack running, archive them through the deferred flow, which creates the archive, uploads each file straight to storage, waits until the consumer has built the archive, and downloads it:

```shell
just archive-deferred notes.txt data.csv --name report
```

Either saves `report.zip` in the current directory. Both run `scripts/archive.py`, which needs nothing beyond Python's standard library; `--help` lists its options.

With `curl` instead, the direct flow is one request:

```shell
curl --form files=@notes.txt --form files=@data.csv --form name=report \
    --output report.zip http://localhost:8000/archive-files
```

The deferred flow takes four, described step by step in [the API page](api.md#deferred-archives):

```shell
curl --json '{"name": "report", "files": [{"name": "notes.txt", "size": 6}]}' \
    http://localhost:8000/archives
curl --upload-file notes.txt '<the upload URL>'
curl '<the status URL>'
curl --output report.zip '<the download URL>'
```

## Set it up for development

uv installs the Python version the project needs, 3.14, if it is not already present.

```shell
uv sync --all-groups
uv run prek install
```

The first command installs every dependency group, including the development tools; the second installs the Git hooks, which check each commit before it is made.

| Recipe                     | What it does                                                        |
|----------------------------|---------------------------------------------------------------------|
| `serve`                    | Serve the API locally, reloading on code changes.                   |
| `up`, `down`               | Start the whole stack and wait until it is healthy; stop it.        |
| `archive`                  | Archive files with the running service in one request.              |
| `archive-deferred`         | Archive files through the deferred flow.                            |
| `test`                     | Run the unit tests, which need no Docker.                           |
| `test-cov`                 | Run the unit tests with a coverage report and the 85% floor.        |
| `test-integration`         | Run the integration tests against the running stack.                |
| `check`                    | Run the lint, formatting, dependency and type checks.               |
| `reformat`                 | Reformat the code and sort the imports.                             |
| `docs`, `build-docs`       | Serve this documentation locally; build it, failing on any warning. |
| `build-image`, `run-image` | Build the Docker image; run it, serving on port 8000.               |

`just --list` shows them all.
