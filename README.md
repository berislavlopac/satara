# Satara

A web service that packs uploaded files into a ZIP archive. In the direct flow, a client sends
its files in a single request and receives the archive in the response, streamed as it is
written. In the deferred flow, for larger archives, the client uploads each file straight to
storage and fetches the archive once a queue consumer has built it.

## Quick start

With Docker:

```shell
docker build -t satara .
docker run --rm -p 8000:8000 satara
```

Then:

```shell
curl --form files=@notes.txt --form files=@data.csv --form name=report \
    --output report.zip http://localhost:8000/archive-files
```

The deferred flow needs storage and the consumer. Docker Compose runs them locally, with an
emulator standing in for S3 and SQS:

```shell
docker compose up -d --build --wait
```

[Getting started](docs/getting-started.md) shows how to try both flows, with
`just archive` and `just archive-deferred`.

For development, with [uv](https://docs.astral.sh/uv/):

```shell
uv sync --all-groups
uv run prek install
uv run just serve
```

## Documentation

The documentation is in [`docs/`](docs/index.md), and is built as a site with
`uv run just docs`, served at <http://localhost:7000>. It covers
[getting started](docs/getting-started.md), [the API](docs/api.md),
[configuration](docs/configuration.md), [deployment](docs/deployment.md),
[CI and quality checks](docs/ci.md) and [the architecture](docs/architecture.md).

## Decisions and trade-offs

Satara was written as a take-home exercise. [The exercise](docs/exercise.md) page summarises the
main trade-offs, what is left out and what would come next, and
[AI-assisted development](docs/ai-assisted-development.md) describes the author's general
practice of developing software with AI assistance.

Every decision is recorded, as it was made, in [DECISIONS.md](DECISIONS.md), including those
later corrected.
