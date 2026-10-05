# Satara Archiver

A web service that packs uploaded files into a ZIP archive. In the direct flow, a client sends
its files in a single request and receives the archive in the response, streamed as it is
written. In the deferred flow, for larger archives, the client uploads each file straight to
storage and fetches the archive once a queue consumer has built it.

## Try it in five minutes

This runs both flows, from a clone to two downloaded archives. On your own machine it needs only [Docker](https://docs.docker.com/get-docker/) with Compose, `curl`, and Python 3.10 or later for the small client script. The service itself runs in the containers, on Python 3.14, with everything it needs inside its image.

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

Satara Archiver was written as a take-home exercise for a senior backend engineering role. The brief is in [take-home-exercise.pdf](docs/take-home-exercise.pdf): build a file-zipping REST API with FastAPI as a proof of concept that will go live and grow, provide a Docker image and a CI/CD pipeline, and describe a way of developing software with AI assistance.

Every decision is recorded, as it was made, in [DECISIONS.md](DECISIONS.md), including those later corrected.

### How the tasks are met

| Task                       | Where                                                                                                           |
|----------------------------|-----------------------------------------------------------------------------------------------------------------|
| 1. File-zipping REST API   | `POST /archive-files`, and `/archives` for larger archives; see [API](docs/api.md).                             |
| 2. Containerisation        | The `Dockerfile`; see [Getting started](docs/getting-started.md).                                               |
| 3. CI/CD pipeline          | GitHub Actions; see [CI and quality checks](docs/ci.md).                                                        |
| 4. AI-assisted development | [AI-ASSISTED-DEVELOPMENT.md](AI-ASSISTED-DEVELOPMENT.md): the author's general practice, not only this project. |

### Main trade-offs

- **Streaming over buffering.** The archive is sent as it is written, so memory stays flat whatever the upload size. The cost is a response without a `Content-Length`, and a failure after the first byte can only cut the connection, so every check is made before it.
- **Hard limits on one request.** The number of files, the size of each and the size of the whole request are capped, which keeps a single request's cost bounded. Archives larger than one request can carry are what the deferred flow is for.
- **A second flow for large archives.** The brief asks for one endpoint; the deferred flow is an addition, switched off by default so the image still runs on its own. Files go straight to storage, and the service never carries their bytes, so its limits are far higher: 1000 files, 5 GiB each and 50 GiB in all by default. The cost is the moving parts: a bucket, a queue, a consumer, and a client that makes several requests rather than one.
- **The bucket as the only state.** Each archive is a manifest written once, and its progress is read from the objects that exist, so nothing is updated in place and no database is needed. A database could take the manifests' place behind the same port.
- **A queue over a webhook.** A queue keeps a message until the consumer deletes it after the build, so a crash means the build is tried again. A webhook would keep the flow to one service, but its sender forgets the event once answered, so a crash during a build would lose it.
- **A simple consumer.** One consumer handles one batch at a time, which rules out building an archive twice without a lock. The queue hides a received message for a long time, 30 minutes in the local stack, rather than the consumer extending it during a build, so a retry, after a crash or a failed attempt, waits that long.
- **Names over content.** A file is identified by its base name. A name already taken is renamed rather than dropped or overwritten, and nothing is deduplicated by content, so two identical files take space twice. Some edge cases are tolerated rather than covered by further rules: a requested archive name of `report.zip` becomes `report.zip.zip`.
- **An archive name of the client's choosing.** The brief does not ask for it; it is an addition, limited to ASCII so it fits a response header without encoding.
- **Existing parts over our own.** The request body limit is Starlette's own middleware. The cost is that its two refusals differ in form, one in plain text and one in JSON.
- **Compression off the request's path.** Compression runs in a worker thread rather than a process: the compression library releases Python's global interpreter lock, so threads give real parallelism, while a process would need every chunk copied to it and back.

### Not included: release, publishing and deployment

The brief asks for CI/CD. This solution stops at CI: it does not release, publish or deploy the service. With a target environment, the next steps would be:

- Publish the image to a registry, such as GitHub's or Amazon's, on every merge to `main`, tagged with the commit.
- Release by tagging a version, promoting the image already built and checked rather than building again for each environment.
- Deploy to AWS: the service and the consumer as containers on ECS Fargate, the service behind a load balancer, with the bucket, the queues and the rest of the infrastructure described in code using CDK or Terraform.

### With more time

- **Authentication.** The endpoints are open to anyone. Behind an API gateway that may do for a proof of concept, but a live service needs it first.
- **Expiry.** Nothing is ever deleted from the bucket. A lifecycle rule would remove uploads and archives after some days.
- **A sturdier consumer:** extending a message's visibility while a build runs, which allows a short timeout and a quick retry after a crash, and a lock so that several consumers can run.
- **Files over 5 GiB** in the deferred flow, uploaded in parts with S3's multipart upload.
- **An alarm on the dead-letter queue**, so that a failed message reaches a person.
- **Observability:** metrics and traces, beside the structured logs the service already writes.
- **Rate limiting**, and the body size limit enforced again at the proxy in front of the service.
- **More archive formats**, as further implementations of the writer port.
- **Telling the client which files were renamed**, for example in a response header.
- **Load tests**, to find out how many concurrent requests one container serves well.

The decisions record also lists [the limits left for production](DECISIONS.md#limits-left-for-production): what a review made as if the service were going to production found, and what would address each.
