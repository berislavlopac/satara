# API

The service packs files into a ZIP archive in one of two ways:

- **Directly**: the client sends its files in one request and receives the archive in the
  response. This suits a modest number of fairly small files.
- **Deferred**: the client declares its files, uploads each straight to storage, and fetches
  the archive once it has been built. This takes many more files, and much larger ones. It is
  served only when switched on; see [Configuration](configuration.md#the-deferred-flow).

## Interactive documentation

The service documents its own API, from the code that serves it, so it always matches the running
version. With the service running locally:

- <http://localhost:8000/docs> lets you read about each endpoint and try it from the browser;
- <http://localhost:8000/openapi.json> is the OpenAPI document, for tools and generated clients.

## Archive files

`POST /archive-files` takes files as `multipart/form-data` and returns them packed into a ZIP
archive.

| Field   | Required | Content                                                         |
|---------|----------|-----------------------------------------------------------------|
| `files` | yes      | The files to pack. Repeat the field once for each file.         |
| `name`  | no       | The name of the archive, without the `.zip` suffix.             |

```shell
curl --form files=@notes.txt --form files=@data.csv --form name=report \
    --output report.zip http://localhost:8000/archive-files
```

### The response

The archive is sent as it is written, so the service never holds a whole archive in memory.

| Header                | Value                                                           |
|-----------------------|-----------------------------------------------------------------|
| `Content-Type`        | `application/zip`                                               |
| `Content-Disposition` | `attachment; filename="<name>.zip"`                             |
| `Cache-Control`       | `no-store`, since the archive holds the client's own files.     |

The response has no `Content-Length`: its size is not known until the archive is complete, so
it is sent in chunks. Every check is made before the first byte is sent. A failure after that,
such as a file that cannot be read, can only cut the connection.

Each file is compressed with deflate. A file of about 2 GiB or more is written with the ZIP64
extensions, which some older unzip tools cannot read.

### File names in the archive

- Each file keeps only its base name: directories in the name it was sent with are dropped.
  Both `/` and `\` count as separators.
- A name holding a control character, such as a NUL byte or a line break, is refused.
- A file whose name is already taken in the archive is renamed by adding `-2`, `-3` and so on
  before the first dot, ignoring a dot at the very start: a second `report.tar.gz` becomes
  `report-2.tar.gz`, and a second `.bashrc` becomes `.bashrc-2`.
- Names that differ only in letter case or Unicode form count as the same name, because the
  default file system of macOS treats them as one, and that of Windows ignores letter case:
  `Report.txt` and `report.txt` become `Report.txt` and `report-2.txt`.
- No file is dropped, and files keep the order in which they were sent.

### The archive's name

A name starts with an ASCII letter or digit, holds only ASCII letters, digits, `-`, `_` and `.`,
and is at most 100 characters long. The `.zip` suffix is always added, even to a name that
already ends with it.

Without a name, or with an empty one, the archive is named after the time it was created, in
UTC: `archive-20261002T143015Z.zip`.

### Refusals

A refused request is answered with a JSON body whose `detail` gives the reason, with one
exception noted below.

| Status | Reason                                                                         |
|--------|--------------------------------------------------------------------------------|
| 400    | A form the form parser cannot read, such as one without its boundary.          |
| 400    | More than 1000 files, or more than 1000 other fields.                          |
| 400    | A field other than a file larger than 1 MiB.                                   |
| 413    | More files than the limit allows.                                              |
| 413    | A file larger than the limit for a single file.                                |
| 413    | A request body larger than the limit for the whole request.                    |
| 422    | No files.                                                                      |
| 422    | A file whose name is empty, `.` or `..` once its directories are dropped.      |
| 422    | A file whose name holds a control character.                                   |
| 422    | An archive name that breaks the rules above.                                   |

For 400 and 413, `detail` is a string. For 422, it is a list of errors in the form the web
framework uses for its own validation, each naming the field at fault in `loc`:

```json
{
  "detail": [
    {"type": "value_error", "loc": ["body", "files"], "msg": "'..' is not a usable file name"}
  ]
}
```

The limits are set in the [configuration](configuration.md).

A body too large is refused as soon as that is known: at once when its declared
`Content-Length` is over the limit, and otherwise as soon as the bytes received pass it, before
the rest is read. The first case is answered in plain text, `Content Too Large`, rather than
JSON.

## Deferred archives

### Create an archive

`POST /archives` takes a JSON body naming the archive and declaring each file to be uploaded.

| Field   | Required | Content                                                            |
|---------|----------|--------------------------------------------------------------------|
| `files` | yes      | The files, each as `{"name": ..., "size": ...}`, size in bytes.    |
| `name`  | no       | The name of the archive, without the `.zip` suffix.                |

```shell
curl --json '{"name": "report", "files": [{"name": "notes.txt", "size": 6}]}' \
    http://localhost:8000/archives
```

It answers `201`, with the status URL also in the `Location` header:

```json
{
  "archive_id": "0199a9f4-7c1e-7d3a-9a51-3c2b7e0d4f10",
  "status_url": "http://localhost:8000/archives/0199a9f4-7c1e-7d3a-9a51-3c2b7e0d4f10",
  "uploads": [{"name": "notes.txt", "url": "http://localhost:4566/..."}]
}
```

Files are named as in the direct flow, so a name in `uploads` may differ from the one
declared. The archive's name follows the same rules too.

### Upload the files

`PUT` each file's content to its URL, for example with `curl --upload-file notes.txt '<url>'`.
Storage accepts a body of exactly the declared size and refuses any other, and a URL expires
after an hour by default. Files can be uploaded in any order, and at the same time. There is
no way to get a fresh upload URL, so an archive whose files are not all uploaded in time stays
`pending`; create a new one instead.

### Fetch the archive

`GET /archives/{id}`, the status URL, reports how far the archive has got:

```json
{
  "archive_id": "0199a9f4-7c1e-7d3a-9a51-3c2b7e0d4f10",
  "status": "ready",
  "files_received": 1,
  "files_expected": 1,
  "download_url": "http://localhost:4566/..."
}
```

| Status    | Meaning                                                                          |
|-----------|----------------------------------------------------------------------------------|
| `pending` | Not built yet: files are still to arrive, or the archive is being built.         |
| `ready`   | Built; `download_url` serves it as `<name>.zip`.                                 |
| `failed`  | Every file arrived, but the archive could not be built in any attempt.           |

The archive is built in the background once its last file arrives, so poll the status URL
until it is no longer `pending`. A download URL expires like an upload URL; asking for the
status again gives a fresh one.

### Refusals

`POST /archives` is refused as the direct flow's endpoint is, with 413 for a broken limit
and 422 for an unusable name or no files, but the limits are the deferred flow's own and the
total size is that of the declared files. Its body may hold 1 KiB for each file allowed, 1000
KiB by default, and a larger one is refused with 413 before it is read in full.

`GET /archives/{id}` answers 404 for an ID no archive has, and 422 for one that is not a UUID.

## Health check

`GET /health` answers `200` with `{"status": "ok"}` while the service is running. The
container's health check uses it.
