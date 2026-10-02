# Agent instructions

Satara is a FastAPI service that packs uploaded files into a ZIP archive. The spec is the PDF
in the repository root.

## Working style

- Work in small increments. Say what is about to change and why, then wait for approval.
- A question is not a work order. Answer it, propose any change it implies, and wait.
- When something breaks, explain the cause first and suggest the fix; do not fix it and
  explain afterwards.
- Check every requirement against the spec text. Do not build on requirements it does not state.
- Write a claim into the documentation only after the code it describes exists, and reread
  the documentation against the code once the code settles.
- Treat a review comment as a claim to verify, preferably by running the code. A comment can
  be right that something is broken and wrong about the cause or the fix.
- Stay on task. Note an incidental problem in one line and move on.

## Tooling

- `uv` manages the environment and `just` runs tasks. Run tools through the recipes
  (`just --list`), not directly. Run any Python through `uv run`, never a bare `python`: the
  system interpreter is a different version.
- Python 3.14. Do not add `from __future__ import annotations`: annotations are already
  evaluated lazily, and turning them into strings is the fragile path for Pydantic.
- pyrefly checks types, ruff lints and formats (line length 96), deptry checks dependencies.
  Run lint and type checks before pushing, and never skip hooks with `--no-verify`.
- Write code already formatted: lines within 96 characters, a trailing newline at the end of
  every file.
- ASCII only in code, comments, docstrings and Markdown documents. String literals that are
  data may hold any character; a test of non-ASCII input should spell it literally.

## Dependencies

- Declare lower bounds only (`pydantic>=2.12`), never an upper bound, and never cap Python.
  The lock file pins exact versions. Cap only for a known incompatibility, and prefer
  excluding the one bad release.
- Prefer the latest versions, upgrading fully rather than pinning around a problem.

## Layout

- The package lives in `satara/`, and the project is not installed as a package
  (`package = false`).
- Layers: `domain`, `application`, `infrastructure`, `presentation`, `wiring`. Each is a single
  module until it outgrows it, then becomes a package.
- Ports are `Protocol`s in the domain; adapters implementing them live in `infrastructure`.
  `wiring` builds services from settings and owns long-lived resources.
- `common` holds generic utilities with no project vocabulary.
- `__init__.py` holds a docstring and nothing else: no re-exports, no `__all__`. Import a
  name from the module that defines it.
- Settings use pydantic-settings in `satara/config.py`, with the `SATARA_` environment prefix.
  Add a field only when something uses it.

## Models

- `FrozenModel` is the mechanism only and is never the direct base of a concrete class. Each
  layer names its own base on top of it: `ValueObject` in the domain, `Command` and `Result`
  in the application, `APIModel` in presentation.
- Name commands and results after the use case: `compress_files(command:
  CompressFilesCommand) -> CompressFilesResult`.
- Entities are mutable, compare and hash by identity, and change only through their own
  methods, never by attribute assignment.
- Wrap a primitive in a value object unless the raw type is clearly better. Pydantic models
  take no positional arguments, so build one from a raw value with `model_validate`.
- Prefer a dunder method where it reads as the domain's own sentence: `len(content)`,
  `item in archive`.
- Domain docstrings describe domain rules only, never where data comes from or which flow
  uses it.

## Code style

- Type annotations are required in source code; tests are exempt. pyrefly is the authority.
- In `match` statements, end with `typing.assert_never` rather than `case _: raise ...`, so
  the checker can prove every case is handled.
- `pathlib`, not `os.path`. Datetimes are always timezone-aware.
- HTTP status codes come from `http.HTTPStatus`, never a numeric literal, in code and in
  tests.

## Naming

- Functions and methods are verbs; values are nouns. If a name needs its docstring to be
  understood, change the name.
- Exceptions: a property is a value and takes a noun (`is_` / `has_` for booleans); a
  conversion may name its result; an accessor should be a property where possible; an
  established, named convention wins.
- `to_` produces a new representation and does work (`to_entity`, `to_json`). `as_` is a
  cheap view of the same data (`as_posix`). Most conversions are `to_`. `with_` returns a copy
  with one thing changed.
- Renaming a symbol that other code imports is an API change: give it a commit of its own.

## Comments and docstrings

- Docstrings are short and plain, in Markdown, with Google-style `Args:` / `Returns:` /
  `Raises:` sections. A base type never lists its subclasses.
- Describe what a thing is or must contain. Name what it excludes by broad category ("no
  path or drive"), not by a list of specific counterexamples.
- `Raises:` lists only exceptions the function raises itself. For a `Protocol`, list what
  implementations must raise.
- Document a Pydantic field with a string literal on the line after it.
- A comment describes the code, not the change that produced it. Avoid "now", "no longer",
  "previously"; state the standing rule. History belongs in the commit message.
- State the observable outcome ("returns the input unchanged", "raises nothing"), not a
  category such as "no-op".
- Refer to a dependency by its role ("the HTTP client"), not its name.
- TODOs take the form `# TODO: ...`, with continuation lines aligned.

## Writing

Applies to everything a person reads: comments, docs, commit messages, pull requests.

- Prefer plain wording to a term of art. If a term is genuinely the right one, define it where
  the reader first meets it.
- One term per concept, used every time. Two words for one thing make the reader check
  whether two things are meant.

## Tests

- Every test directory is a package, with an `__init__.py`.
- A test name, with `test_` dropped and underscores turned into spaces, reads as a sentence
  describing the behaviour: `test_compress_files_refuses_an_empty_request`.
- `pytest --spec` renders test docstrings, so the first line is a complete one-line summary
  followed by a blank line. A summary wrapped over two lines prints a dangling fragment.
- Test through the public surface. Do not import private helpers into tests.
- Tests are not type-checked: they prove themselves by running, and annotating them invites a
  fight with every double. The test doubles are the exception. They live in
  `tests/unit/fakes.py`, the one test path pyrefly checks, and each subclasses the protocol
  it stands in for, so a double cannot drift from it.
- Tests get their doubles from fixtures and never import them. Fixtures live in
  `conftest.py` at the level where they are shared, or in the test module that alone uses
  them. A fixture may return an instance, a class or a factory; a fixture a Hypothesis test
  needs is session-scoped, since Hypothesis cannot use a function-scoped one.

## Commits

- Small, focused commits with a lowercase imperative subject; the body explains why.
- Branch names use `-` as the only separator.
