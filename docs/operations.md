# Running it

## Configuration

The service is configured through environment variables, or a `.env` file in its working
directory. Other variables are ignored.

| Variable                | Default  | Limit                                                  |
|-------------------------|----------|--------------------------------------------------------|
| `SATARA_MAX_FILES`      | 100      | The most files a single request may upload.            |
| `SATARA_MAX_FILE_SIZE`  | 50 MiB   | The largest size of a single uploaded file.            |
| `SATARA_MAX_TOTAL_SIZE` | 200 MiB  | The largest size of a request body.                    |

A size may carry a unit: `50MiB` is 50 * 1024 * 1024 bytes, `50MB` is 50 * 1000 * 1000, and a
bare number is in bytes. A limit of zero is refused when the service starts, and so are more
than 1000 files, the most the form parser accepts, or a file size over 2000 MiB, the most the
archive format holds (see [the response](api.md#the-response)).

```shell
docker run --rm -p 8000:8000 -e SATARA_MAX_FILES=20 satara
```

## The container

The image is built in two stages: the first installs the locked runtime dependencies, and the
second holds only those and the service's code, without the build tools or the tests.

- The service runs as an unprivileged user, as a single server process listening on port 8000.
  To serve more requests, run more containers.
- A health check calls `GET /health` every 30 seconds.
- On a stop signal the server finishes cleanly.

Uploaded files larger than 1 MiB are written to temporary files under `/tmp` while a request is
read. A container run with a read-only filesystem therefore needs a writable `tmpfs` mounted on
`/tmp`, large enough for the total size limit times the number of requests served at once.

## Checks

The same checks run in two places, through the same `just` recipes and the same locked tool
versions.

| Where                        | When                                  | What                                                                      |
|------------------------------|---------------------------------------|---------------------------------------------------------------------------|
| Git hooks, run by prek       | Before each commit                    | File hygiene, then the lint, formatting, dependency and type checks.      |
| GitHub Actions, `ci.yml`     | Every pull request and push to `main` | The same checks, the tests with the coverage floor, and the Docker image. |
| GitHub Actions, `docs.yml`   | Changes to the documentation          | This documentation, built with every warning treated as an error.         |

The hooks catch problems before a commit exists, but they can be skipped or never installed;
CI cannot. The tests run only in CI, since slow hooks get skipped.

CI does not stop at building the image: it starts it, waits for its health check to pass, and
sends one real upload.

Dependabot proposes weekly updates for the GitHub Actions, the Docker base images and the
Python dependencies, and opens pull requests for security fixes.
