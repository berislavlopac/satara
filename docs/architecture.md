# How it's built

## Layers

The code in `satara/` is split into layers, each a single module until it outgrows one and
becomes a package. A layer depends only on the ones above it in this list.

| Layer            | Module              | Holds                                                                  |
|------------------|---------------------|------------------------------------------------------------------------|
| Domain           | `domain.py`         | The archive, the rules for its names, and the ports it is written through. |
| Application      | `application/`      | The use case, `archive_files`: the limits, and building the archive.  |
| Infrastructure   | `infrastructure/`   | The ZIP writer, which implements the domain's writer port.            |
| Presentation     | `presentation/`     | The HTTP endpoints and the answers to refused requests.               |
| Wiring           | `wiring.py`         | Builds the application from its settings.                             |

Settings are read in `config.py`. `common/` holds generic utilities with no project vocabulary.

## Ports

The domain declares two protocols that the rest of the code meets:

- `Content` is the bytes of a file, read in chunks. An uploaded file meets it directly, and the
  tests use an in-memory one.
- `ArchiveWriter` writes an archive in one format, producing its bytes as they are ready. It
  also names the format's media type and file suffix, which the response headers use.

The application depends only on `ArchiveWriter`, never on ZIP. Another format would be a second
implementation of it, chosen where the application is built.

## A request, end to end

1. **The body size guard**, Starlette's request body limit middleware, refuses a body larger
   than the total size limit as it arrives, before the form parser stores it.
2. **The form parser** reads the files, writing any larger than 1 MiB to temporary files.
3. **The endpoint** turns each upload into an `UploadedFile` and calls `archive_files`.
4. **The service** checks the number of files and the size of each, keeps each file's base
   name, and adds the files to an `Archive`, which renames any whose name is taken. It reads no
   content: it returns the writer's output unread, so every check is complete before the
   response starts.
5. **The response** streams the writer's output. The ZIP writer reads each file in 64 KiB
   chunks and compresses each chunk in a worker thread, so compression does not hold up other
   requests, and sends what it has written after each chunk.

A refusal from the service is raised as an exception and answered by one handler in the
presentation layer, which picks the status: 413 for a broken limit, 422 for anything else.

## Tests

The tests in `tests/unit/` cover each layer through its public surface, from the domain's naming
rules, partly with generated inputs, to the whole application driven through the test client
with the real ZIP writer.

They are written to be read as well as run: a test's name reads as a sentence describing the
behaviour, and its body shows how the code is used. The test doubles live in
`tests/unit/fakes.py` and reach the tests through fixtures. They are the only test code that is
type-checked, each one built on the protocol it stands in for, so that it cannot drift from it.
