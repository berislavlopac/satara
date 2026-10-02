# Decisions

A record of the decisions behind this service, in the order they were made. A decision that
is later reversed stays here, with a note of what replaced it.

## 2026-10-01

### Two flows: direct and deferred

The spec asks for one endpoint that receives files, zips them and returns the archive in a
single request. That works only for a limited number of fairly small files, so the service
will offer two flows:

- **Direct**: the endpoint from the spec, with hard limits on file count and size.
- **Deferred**: the client receives a presigned upload URL for each file, plus a status URL
  that ends up showing a presigned download URL for the archive. The deferred flow can be
  switched off with a setting, and is off by default, so the image runs on its own without
  any storage service.

The direct flow is built completely first, with its Docker image, CI and documentation,
before any work on the deferred flow starts.

### Archive formats behind a port

Writing an archive is a port (a `Protocol` the application depends on), with ZIP as the only
adapter. Other formats can be added as adapters without changing the application.

### Flat layout, layers as modules

The package lives in `satara/` and is not installed. Each layer (`domain`, `application`,
`infrastructure`, `presentation`, `wiring`) is a single module until it outgrows it.

### A file is identified by its name in the archive

Only the base name of an uploaded file is kept; the uploader's directories are dropped. Both
`/` and `\` count as separators whatever platform the service runs on, because some Windows
tools treat a backslash in an archive entry as a directory, so `..\..\file` could otherwise
be extracted outside the target folder.

Names in an archive are unique. When a name is already taken, the new file is renamed by
adding `-N` before the first dot, using the smallest `N` from 2 that is free: `foo.tar.gz`
becomes `foo-2.tar.gz`. A dot at the very start of a name does not count, so `.bashrc`
becomes `.bashrc-2`. Files are handled in the order they arrive, and no file is ever dropped.

This replaces identifying a file by its checksum. Nothing in the spec asks for content-based
uniqueness, and without it the direct flow needs no checksums at all. The cost is that two
identical files take space twice in the archive.

Some edge cases are accepted rather than covered by extra rules. For example, a request of
`foo.txt`, `foo.txt`, `foo-2.txt` gives `foo.txt`, `foo-2.txt`, `foo-2-2.txt`: the client's
own `foo-2.txt` is the one renamed.

### Limits, and where they are enforced

The limits are settings: file count, size of a single file, and total size, starting at 100
files, 50 MiB and 200 MiB.

The upload parser writes every file to temporary storage before the endpoint runs, and it
limits only the number of files and fields, not their size. A total-size limit checked inside
the endpoint would come after the whole upload is already on disk. So the total size is
enforced while the request body arrives: a request whose `Content-Length` already exceeds it
is refused at once, and any other is refused as soon as the bytes read pass it. Both are
refused with 413. The other limits are checked in the application service, where the
total-size limit already bounds the cost of a request that breaks them.

### The direct flow streams its response

The archive is written to the response as it is produced, so memory use stays flat. Once
streaming starts, the status and headers have been sent, and a failure can only cut the
connection. So every decision (limits, names, renames) is made before the first byte, and
the archive writer only writes. The response carries no `Content-Length`, since the size is
not known in advance.

### Property-based tests for the archive rules

The naming rules are invariants: every file appears once, names are unique, a name that did
not collide is unchanged. They are tested with generated inputs (Hypothesis) as well as
examples.

### Checks run before commit and on every change to `main`

The codebase will soon have several contributors, so the same checks run in two places:
pre-commit hooks on each contributor's machine, which catch problems before they are
committed, and GitHub Actions on pull requests and merges, which cannot be skipped.

### Deferred flow: first choices

These will be revisited when work on the deferred flow starts.

- Storage is a port, with S3 as the adapter; an S3 emulator in Docker Compose stands in for
  AWS locally.
- Uploads use presigned POST, which can limit the size of an upload. If the emulator does not
  support it, presigned PUT without a size limit is the fallback, recorded as a trade-off.
- Each archive has its own directory in the bucket, named by the archive ID, holding a
  manifest written once at creation.
- The bucket sends a notification for each upload to a queue, read by a consumer that runs as
  a separate service.
- The archive is built once, when the last file has arrived. Adding each file as it arrives
  was rejected: stored objects cannot be appended to, so each addition would rewrite the whole
  archive, and concurrent notifications would race to do it.
- If checksums are needed, the algorithm is a setting, using the standard library.
  `pychecksumtool` was rejected: it requires `pytest<9` at runtime, which conflicts with this
  project's test dependencies.

## 2026-10-02

### The client may name the archive

The spec asks only for appropriate response headers, which a generated name would satisfy.
Letting the client choose the name is an addition of ours: a request may carry an optional
archive name, and the download is offered under it, with the format's suffix added.

A name starts with an ASCII letter or digit and holds only ASCII letters, digits, `-`, `_` and
`.`, up to 100 characters. ASCII keeps the name usable in the `Content-Disposition` header
without the encoded second form that other characters need, and the first character rules out
hidden files and `..`. Without a name, the archive is named after the time it was created, in
UTC: `archive-20261002T143015Z`.

The suffix is always added, so a requested `report.zip` is offered as `report.zip.zip`. That is
accepted as an edge case rather than handled with a rule that depends on the format.

## Build order for the direct flow

Each step is a separate, reviewed commit or small group of commits.

1. Settings, with the limits.
2. Domain model: the archive and its entries, the naming rules, property tests.
3. Archive writer port and the ZIP adapter.
4. Application service: checks the limits and builds the archive.
5. Size guard for the request body.
6. Endpoint, error responses, application wiring, a `serve` recipe.
7. Docker image.
8. CI pipeline and pre-commit hooks.
9. README and the AI development write-up.
