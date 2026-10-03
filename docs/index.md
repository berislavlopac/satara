# Satara

Satara is a web service that packs uploaded files into a ZIP archive, in one of two ways. In the
direct flow, a client sends its files in a single request and receives the archive in the
response, streamed as it is written. In the deferred flow, a client uploads each file straight
to storage, and a queue consumer builds the archive once the last one has arrived, which takes
many more files and much larger ones.

It is a FastAPI application and a queue consumer, both run from one Docker image.

## Where to start

- [Getting started](getting-started.md): run the service or the whole stack locally, try both flows, and set it up for development.
- [API](api.md): the endpoints, their fields, their responses and the reasons a request is refused.
- [Configuration](configuration.md): every setting, debug mode, and what the logs hold.
- [Deployment](deployment.md): what running it for real needs: the two processes, storage and queues.
- [CI and quality checks](ci.md): the checks before each commit and in CI, and how dependencies are kept current.
- [Architecture](architecture.md): the layers of the code, the ports, and how each flow runs through them.
- [AI-assisted development](ai-assisted-development.md): how the author develops software with
  AI assistance, in general; written as the answer to the brief's fourth task.
- [The exercise](exercise.md): the take-home exercise this service was written for, its
  trade-offs and next steps.
