# Satara

Satara is a web service that packs uploaded files into a ZIP archive. A client sends its files
in a single request and receives the archive in the response, streamed as it is written.

It is a FastAPI application, run as a Docker container.

## Where to start

- [Getting started](getting-started.md): run the service with Docker, or set it up for
  development.
- [Using the API](api.md): the endpoint, its fields, its responses and the reasons a request is
  refused.
- [Running it](operations.md): configuration, the container, and the checks that guard the
  code.
- [How it's built](architecture.md): the layers of the code and how a request flows through
  them.
- [AI-assisted development](ai-assisted-development.md): how the author develops software with
  AI assistance, in general; written as the answer to the brief's fourth task.
- [The exercise](exercise.md): the take-home exercise this service was written for, its
  trade-offs and next steps.
