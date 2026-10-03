# Satara

A web service that packs uploaded files into a ZIP archive. In the direct flow, a client sends
its files in a single request and receives the archive in the response, streamed as it is
written. In the deferred flow, for larger archives, the client uploads each file straight to
storage and fetches the archive once a queue consumer has built it.

## Try it in five minutes

All it needs is [Docker](https://docs.docker.com/get-docker/) with Compose, `curl`, and Python 3.10 or later. This runs both flows, from a clone to two downloaded archives:

```shell
git clone https://github.com/berislavlopac/satara.git && cd satara
docker compose up -d --build --wait     # the API, the consumer, emulated S3 and SQS

printf 'hello\n' > notes.txt && printf '1,2\n3,4\n' > data.csv

# The direct flow: one request, and the ZIP comes back
curl --form files=@notes.txt --form files=@data.csv --form name=direct \
    --output direct.zip http://localhost:8000/archive-files
unzip -l direct.zip

# The deferred flow: declare the files, upload them to storage, wait for the build, download
python3 scripts/archive.py --deferred notes.txt data.csv --name deferred
unzip -l deferred.zip

docker compose down
```

While the stack runs, the service documents its own API at <http://localhost:8000/docs>, where each endpoint can be tried from the browser. `scripts/archive.py` needs nothing beyond Python's standard library; `python3 scripts/archive.py --help` lists its options, and without `--deferred` it uses the direct flow.

## Develop it

With [uv](https://docs.astral.sh/uv/), which also brings [just](https://just.systems) for the project's tasks:

```shell
uv sync --all-groups
uv run prek install
uv run just --list
```

`uv run just up` starts the stack, and `uv run just archive` and `uv run just archive-deferred` run the client script. [Getting started](docs/getting-started.md) has the details.

## Documentation

The documentation is in [`docs/`](docs/index.md). To read it as a site, run `uv run just docs` and open <http://localhost:7000>. It covers [getting started](docs/getting-started.md), [the API](docs/api.md), [configuration](docs/configuration.md), [deployment](docs/deployment.md), [CI and quality checks](docs/ci.md) and [the architecture](docs/architecture.md).

## Decisions and trade-offs

Satara was written as a take-home exercise. [The exercise](docs/exercise.md) page summarises the
main trade-offs, what is left out and what would come next, and
[AI-assisted development](docs/ai-assisted-development.md) describes the author's general
practice of developing software with AI assistance.

Every decision is recorded, as it was made, in [DECISIONS.md](DECISIONS.md), including those
later corrected.
