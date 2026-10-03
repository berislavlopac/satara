# The exercise

Satara was written as a take-home exercise for a senior backend engineering role. The brief is
in [take-home-exercise.pdf](take-home-exercise.pdf): build a file-zipping REST API with FastAPI
as a proof of concept that will go live and grow, provide a Docker image and a CI/CD pipeline,
and describe a way of developing software with AI assistance.

The decisions behind the solution, including those since corrected, are recorded as they were
made in [DECISIONS.md](https://github.com/berislavlopac/satara/blob/main/DECISIONS.md).

## How the tasks are met

| Task                       | Where                                                                          |
|----------------------------|--------------------------------------------------------------------------------|
| 1. File-zipping REST API   | `POST /archive-files`, and `/archives` for larger archives; see [API](api.md). |
| 2. Containerisation        | The `Dockerfile`; see [Getting started](getting-started.md).                   |
| 3. CI/CD pipeline          | GitHub Actions; see [CI and quality checks](ci.md).                            |
| 4. AI-assisted development | [AI-assisted development](ai-assisted-development.md).                         |

## Main trade-offs

- **Streaming over buffering.** The archive is sent as it is written, so memory stays flat
  whatever the upload size. The cost is a response without a `Content-Length`, and a failure
  after the first byte can only cut the connection, so every check is made before it.
- **Hard limits on one request.** The number of files, the size of each and the size of the
  whole request are capped, which keeps a single request's cost bounded. Archives larger than
  one request can carry are what the deferred flow is for.
- **A second flow for large archives.** The brief asks for one endpoint; the deferred flow is
  an addition, switched off by default so the image still runs on its own. Files go straight
  to storage, and the service never carries their bytes, so its limits are far higher: 1000
  files, 5 GiB each and 50 GiB in all by default. The cost is the moving parts: a bucket, a
  queue, a consumer, and a client that makes several requests rather than one.
- **The bucket as the only state.** Each archive is a manifest written once, and its progress
  is read from the objects that exist, so nothing is updated in place and no database is
  needed. A database could take the manifests' place behind the same port.
- **A queue over a webhook.** A queue keeps a message until the consumer deletes it after the
  build, so a crash means the build is tried again. A webhook would keep the flow to one
  service, but its sender forgets the event once answered, so a crash during a build would
  lose it.
- **A simple consumer.** One consumer handles one batch at a time, which rules out building
  an archive twice without a lock. The queue hides a received message for 30 minutes rather
  than the consumer extending it during a build, so a retry after a crash waits that long.
- **Names over content.** A file is identified by its base name. A name already taken is
  renamed rather than dropped or overwritten, and nothing is deduplicated by content, so two
  identical files take space twice. Some edge cases are tolerated rather than covered by
  further rules: a requested archive name of `report.zip` becomes `report.zip.zip`.
- **An archive name of the client's choosing.** The brief does not ask for it; it is an
  addition, limited to ASCII so it fits a response header without encoding.
- **Existing parts over our own.** The request body limit is Starlette's own middleware. The
  cost is that its two refusals differ in form, one in plain text and one in JSON.
- **Compression off the request's path.** Compression runs in a worker thread rather than a
  process: the compression library releases Python's global interpreter lock, so threads give
  real parallelism, while a process would need every chunk copied to it and back.

## Not included: release, publishing and deployment

The brief asks for CI/CD. This solution stops at CI: it does not release, publish or deploy the
service. With a target environment, the next steps would be:

- Publish the image to a registry, such as GitHub's or Amazon's, on every merge to `main`,
  tagged with the commit.
- Release by tagging a version, promoting the image already built and checked rather than
  building again for each environment.
- Deploy to AWS: the service and the consumer as containers on ECS Fargate, the service behind
  a load balancer, with the bucket, the queues and the rest of the infrastructure described in
  code using CDK or Terraform.

## With more time

- **Authentication.** The endpoints are open to anyone. Behind an API gateway that may do for a
  proof of concept, but a live service needs it first.
- **Expiry.** Nothing is ever deleted from the bucket. A lifecycle rule would remove uploads and
  archives after some days.
- **A sturdier consumer:** extending a message's visibility while a build runs, which allows a
  short timeout and a quick retry after a crash, and a lock so that several consumers can run.
- **Files over 5 GiB** in the deferred flow, uploaded in parts with S3's multipart upload.
- **An alarm on the dead-letter queue**, so that a failed message reaches a person.
- **Observability:** metrics and traces, and structured logs from the API as well as the
  consumer.
- **Rate limiting**, and the body size limit enforced again at the proxy in front of the
  service.
- **More archive formats**, as further implementations of the writer port.
- **Telling the client which files were renamed**, for example in a response header.
- **Load tests**, to find out how many concurrent requests one container serves well.
