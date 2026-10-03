# Using the API

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

Each file is compressed with deflate. The archive is written without the ZIP64 extensions, so
a file must stay under 2 GiB even after compression, and compression makes a file that does not
compress slightly larger. The limit for a single file can therefore be set to at most 2000 MiB.

### File names in the archive

- Each file keeps only its base name: directories in the name it was sent with are dropped.
  Both `/` and `\` count as separators.
- A name holding a control character, such as a NUL byte or a line break, is refused.
- A file whose name is already taken in the archive is renamed by adding `-2`, `-3` and so on
  before the first dot, ignoring a dot at the very start: a second `report.tar.gz` becomes
  `report-2.tar.gz`, and a second `.bashrc` becomes `.bashrc-2`.
- Names that differ only in letter case or Unicode form count as the same name, because the
  default file systems of macOS and Windows treat them as one: `Report.txt` and `report.txt`
  become `Report.txt` and `report-2.txt`.
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

The limits are set in the [configuration](operations.md#configuration).

A body too large is refused as soon as that is known: at once when its declared
`Content-Length` is over the limit, and otherwise as soon as the bytes received pass it, before
the rest is read. The first case is answered in plain text, `Content Too Large`, rather than
JSON.

## Health check

`GET /health` answers `200` with `{"status": "ok"}` while the service is running. The
container's health check uses it.

## Interactive documentation

The service describes its own API at `/docs`, and as an OpenAPI document at `/openapi.json`.
