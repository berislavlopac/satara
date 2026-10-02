# The exercise

Satara was written as a take-home exercise for a senior backend engineering role. The brief is
in [take-home-exercise.pdf](take-home-exercise.pdf): build a file-zipping REST API with FastAPI
as a proof of concept that will go live and grow, provide a Docker image and a CI/CD pipeline,
and describe a way of developing software with AI assistance.

The decisions behind the solution, including those since corrected, are recorded as they were
made in [DECISIONS.md](https://github.com/berislavlopac/satara/blob/main/DECISIONS.md).

## How the tasks are met

| Task                          | Where                                                                        |
|-------------------------------|------------------------------------------------------------------------------|
| 1. File-zipping REST API      | `POST /archive-files`; see [Using the API](api.md).                          |
| 2. Containerisation           | The `Dockerfile`; see [Getting started](getting-started.md).                 |
| 3. CI/CD pipeline             | GitHub Actions; see [Running it](operations.md#checks).                      |
| 4. AI-assisted development    | [AI-assisted development](ai-assisted-development.md).                      |

## Main trade-offs

- **Streaming over buffering.** The archive is sent as it is written, so memory stays flat
  whatever the upload size. The cost is a response without a `Content-Length`, and a failure
  after the first byte can only cut the connection, so every check is made before it.
- **Hard limits on one request.** The number of files, the size of each and the size of the
  whole request are capped, which keeps a single request's cost bounded. Archives larger than
  one request can carry are what the deferred flow, below, is for.
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
- Deploy to AWS: the service as a container on ECS Fargate behind a load balancer, with the
  infrastructure described in code using CDK or Terraform.

## With more time

- **The deferred flow**, already designed: the client receives a presigned upload URL for each
  file and a status URL that ends up offering a presigned download URL for the archive.
  Uploads go straight to S3, a queue consumer builds the archive once the last file has
  arrived, and the size of an archive is no longer bounded by a single request. It is planned
  to be switchable off by configuration.
- **Authentication.** The endpoint is open to anyone. Behind an API gateway that may do for a
  proof of concept, but a live service needs it first.
- **Observability:** structured logs, metrics and traces.
- **Rate limiting**, and the body size limit enforced again at the proxy in front of the
  service.
- **More archive formats**, as further implementations of the writer port.
- **Telling the client which files were renamed**, for example in a response header.
- **Load tests**, to find out how many concurrent requests one container serves well.
