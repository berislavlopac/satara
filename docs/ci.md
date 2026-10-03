# CI and quality checks

The same checks run in two places, through the same `just` recipes and the same locked tool versions.

| Where                      | When                                  | What                                                                                           |
|----------------------------|---------------------------------------|------------------------------------------------------------------------------------------------|
| Git hooks, run by prek     | Before each commit                    | File hygiene, then the lint, formatting, dependency and type checks.                           |
| GitHub Actions, `ci.yml`   | Every pull request and push to `main` | The same checks, the unit tests with the coverage floor, the image, and the integration tests. |
| GitHub Actions, `docs.yml` | Changes to the documentation          | This documentation, built with every warning treated as an error.                              |

The hooks catch problems before a commit exists, but they can be skipped or never installed; CI cannot. The tests run only in CI, since slow hooks get skipped.

## The jobs in CI

- **Lint, types and tests:** the checks, then the unit tests with a coverage floor of 85%. The unit tests need no Docker: the S3 and SQS adapters run against an AWS emulator started inside the test process.
- **Docker image:** builds the image, starts it, waits for its health check to pass, and archives one real upload, so it shows the image serves requests and not only that it builds.
- **Integration tests:** start the local Compose stack and run the integration tests against it. They show what only a full emulator can: storage refusing an upload of the wrong size, a download served under its name, and an archive taken through the whole deferred flow.

Third-party actions are pinned to commits, since a tag can be moved to other code.

## Updates

Dependabot proposes weekly updates for the GitHub Actions, the Docker base images, the images in the local stack and the Python dependencies, and opens pull requests for security fixes.
