# Satara

A web service that packs uploaded files into a ZIP archive. A client sends its files in a single
request and receives the archive in the response, streamed as it is written.

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

For development, with [uv](https://docs.astral.sh/uv/):

```shell
uv sync --all-groups
uv run prek install
uv run just serve
```

## Documentation

The documentation is in [`docs/`](docs/index.md), and is built as a site with
`uv run just docs`, served at <http://localhost:7000>. It covers
[getting started](docs/getting-started.md), [using the API](docs/api.md),
[running the service](docs/operations.md) and [how it's built](docs/architecture.md).

## Decisions and trade-offs

Satara was written as a take-home exercise. [The exercise](docs/exercise.md) page summarises the
main trade-offs, what is left out and what would come next, and
[AI-assisted development](docs/ai-assisted-development.md) describes the author's general
practice of developing software with AI assistance.

Every decision is recorded, as it was made, in [DECISIONS.md](DECISIONS.md), including those
later corrected.
