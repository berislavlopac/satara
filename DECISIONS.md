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
enforced while the request body arrives, by Starlette's middleware (see 2026-10-02): a request
whose `Content-Length` already exceeds it is refused at once, and any other is refused as soon
as the bytes read pass it. Both are refused with 413. The other limits are checked in the
application service, where the total-size limit already bounds the cost of a request that
breaks them.

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

### The direct endpoint is a call, not a resource

The direct flow is `POST /archive-files`, named after the use case it runs. It creates nothing
the client can fetch again, so it is a remote call rather than a resource, and the path says
so. `/archives` is left for the deferred flow, where an archive does become a resource with an
address and a status.

### Refusals and response headers

A refused upload is answered with a JSON body naming the reason, except for one case of the body
size guard, described below. A broken limit (too many files, a file too large, a body too large)
is 413 Content Too Large; anything else the client sent that cannot be used (no files, an
unusable file or archive name) is 422.

The archive is sent as an attachment under its name, with `Cache-Control: no-store`, since it
holds the client's own files and no cache along the way should keep a copy. It carries no
`Content-Length`, being streamed.

### The body size guard is Starlette's

Starlette, which FastAPI is built on, has a middleware for exactly the total-size limit: it
refuses a body whose declared length is too large, and otherwise counts the bytes as they
arrive. The service uses it rather than one of its own. Its two refusals differ in form: a
body declared too large gets a plain-text 413, one that grows too large a JSON 413. Both carry
the right status, so the difference is accepted.

### The server

The service runs under uvicorn with its standard extras, which add a faster event loop and HTTP
parser.

### The Docker image

The image follows uv's documented pattern in two stages. The first, on uv's own image, installs
the locked runtime dependencies into a virtual environment; the dev and test groups stay out.
The second, on the plain Python image that uv's is based on, receives only that environment and
the `satara` package, so the image holds neither uv nor the build tools nor the tests.

The service runs as an unprivileged user, as a single server process per container: it scales
by running more containers. The server is started without a shell in between, so it receives
the stop signal and shuts down cleanly. Settings come from `SATARA_` environment variables.

The image declares a health check against `GET /health`, an endpoint added for it. A check that
only opened the port would not show whether the application answers. The endpoint is
operational, not part of the API the spec asks for.

The uv image is pinned to an exact version and the Python image to its `3.14-slim-trixie` tag.
A pinned image is to the build what the lock file is to the dependencies. Dependabot keeps both
current, so the uv in the image may be newer than the one a developer has installed.

The build context is an allow-list: only `pyproject.toml`, `uv.lock` and the package are sent
to the build, so nothing local leaks into the image and unrelated edits keep the cached layers.

### What the checks run, and where

This fills in the decision of 2026-10-01 that checks run before commit and on every change to
`main`.

Before each commit, Git hooks run hygiene checks on the changed files, then the lint and type
check recipes. They take seconds and catch problems before a commit exists. The tests are not
in the hooks: they would make them slower as the suite grows, and slow hooks get skipped.

CI runs on GitHub Actions for every pull request to `main` and every push to `main`, since
hooks can be skipped or never installed. It runs the lint and type checks again, then the tests
with the coverage floor, then the Docker image: built, started, waited on until its health
check passes, and sent one real upload, which shows that the image serves requests and not
only that it builds.

The hooks and CI call the same `just` recipes through `uv`, so each command, its flags and the
tool versions are defined once, in the recipes and the lock file. `just` itself is a locked
dev dependency. Third-party actions are pinned to commits, since a tag can be moved to other
code, and Dependabot proposes weekly updates for the actions, the base images and the Python
dependencies.

The hooks are run by prek, a newer and faster replacement for pre-commit that reads the same
configuration. It is chosen partly to try it out. The configuration uses prek's built-in
hygiene hooks, so it needs prek rather than pre-commit.

### No release, publishing or deployment

The spec asks for CI/CD. This solution stops at CI: it does not release, publish or deploy the
service. With a target environment, the next steps would be:

- Publish the image to a registry, such as GitHub's or Amazon's, on every merge to `main`,
  tagged with the commit.
- Release by tagging a version, promoting the image already built and checked rather than
  building again for each environment.
- Deploy to AWS, where the deferred flow's S3 storage already points: the service as a
  container on ECS Fargate behind a load balancer, with the infrastructure described in code
  using CDK or Terraform.

## 2026-10-03

### File names hold no control characters

A file name holding a control character is refused. The ZIP library cuts a name off at a NUL
byte, so `a.txt` and `a.txt` followed by a NUL and more text were two names to the service but
one in the archive, and one file was lost on extraction. Refusing the whole category, rather
than NUL alone, also keeps line breaks and terminal escapes out of names.

A property test writes names drawn from all of Unicode and checks that each comes back from
the archive unchanged, so any other character the format alters would show up there.

### Names that differ only in case or Unicode form clash

Names that differ only in letter case, or only in how Unicode spells the same character (an
accented letter as one character, or as a letter followed by a combining accent), count as the
same name, so the second is renamed.
The renaming rule exists so that extracting an archive replaces no file, and the default file
systems of macOS and Windows treat such names as one. Each file keeps its own spelling.

### No limit on the length of a file name

A name longer than a file system allows, usually 255 bytes, is kept as it is. The archive holds
it without trouble; only that one file fails to extract on the client's machine. A cap would
have to shorten names when renaming, or a name just under it would break the cap once `-2` is
added, and that rule is more than this edge case is worth.

## Build order for the direct flow

Each step is a separate, reviewed commit or small group of commits.

1. Settings, with the limits.
2. Domain model: the archive and its entries, the naming rules, property tests.
3. Archive writer port and the ZIP adapter.
4. Application service: checks the limits and builds the archive.
5. Size guard for the request body. Folded into step 6: Starlette already provides the
   guard, so all that remained was to switch it on where the application is built.
6. Endpoint, error responses, application wiring, the body size guard, a `serve` recipe.
7. Docker image.
8. CI pipeline and pre-commit hooks.
9. README and the AI development write-up.
