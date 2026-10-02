# How I use AI for Development

## The Workflow

I use Claude Code as my primary agentic coding environment, and my workflow is to treat it as my coding partner.

I start by providing any upfront context I can; in the example of this particular task, I wrote some basic domain model definitions, and an introductory prompt describing - on a high level - the goals and the ideas about the project. I also included the task specification PDF file for full context, and I pointed the agent to my global collection of rules and conventions I use in all of my coding projects.

The next step is a conversation about the possible architectural approaches, as well as any additional concerns. I generally drive this conversation, making decisions myself rather than blindly accepting Claude's suggestions; in the majority of cases I will have a clear idea what needs to be done, but often Claude can provide insights and especially quick sanity checks (e.g. in this project it quickly ran some compressions to give the concrete figures) that would be too time-consuming otherwise. In this particular project, one big topic was scalability; I had a clear idea to have a separate "asynchronous" implementation for that purpose, but Claude helped me clear up some rough edges.

Finally, Claude writes the code in a series of steps, with me providing directions and clarifications during the process. In this example I pushed on some decisions - for example, using Starlette's built-in middleware instead building a custom one, or requiring more clarity in the docstrings.

Claude Code is the main tool I use (normally in the Linux terminal), although I have been experimenting with alternative setups, like using `pi` as the coding harness and open-weight models (like Qwen) running on a local GPU machine.

Additionally, I have been building some agentic solutions using frameworks like CrewAI and Pydantic AI, but primarily as proofs-of-concept and learning exercises.


## Quality

As a baseline, I have a number of tools and requirements I insist on in any project I work on, and which are added and configured before writing any serious code. That includes things like:

- `uv` as the main environment and dependency manager
- `ruff` as the main linter, with a collection of standard checks customised for the needs of a particular project
- `deptry` for checking direct and transitive dependencies
- `pyrefly` for type-checking of production code (tests are never type-checked)
- `pytest`, `pytest-cov`, `pytest-spec` and other related testing tools
- `tox` for running tests against multiple Python versions (when building a library, not in this project)
- `just` for collecting commonly used commands and scripts in one place
- `pre-commit` (or `prek`) for automated code validation before committing

On top of the above, I make sure that every functionality is covered by several layers of tests, with unit tests being the absolute minimal requirement. I use a number of proven unit testing practices such as test doubles (mocks, fakes, dummies etc), fixtures, parametrisation and the like.

Other layers can include some combination of:

- integration tests: executed locally against a docker-compose configuration to test against any required external services, either built as actual services (e.g. postgres) or as an emulation (e.g. AWS services like S3).
- property tests: usually a part of the unit test layer, they use `hypothesis` to test code invariants instead of using fixed oracle values
- mutation tests: validating the quality of other tests, mutation tests change the code under test to confirm that it's actually being covered by tests
- meta-tests: Tests that are not testing functionality, but rather some more abstract concerns that are easy to get lost otherwise. For example, sometimes it is unavoidable to have some configuration stated in two separate places (e.g. an environment variable in `docker compose` and in CI pipelines); meta-tests can ensure that they are always synced and prevent any drift.

With regards to ensuring quality of AI-generated code, I follow a number of techniques as part of my workflow:

- **Small increments:** Every step is proposed and explained, and I approve it before any code is written. Nothing is committed or pushed without my acknowledgement.
- **Explanations before fixes:** When something breaks, the cause comes first and the fix waits for your decision.
- **Any claims are checked against the code, ideally by running it:** That applies to my own claims as much as ones from a PR review. Examples from this project:
  - the compression question was settled by measuring throughput, not by assumption;
  - a test that would have passed for the wrong reason was caught and rebuilt;
  - a networking failure was traced to its cause before anything was changed.
- **The same checks apply to code from any author:** The hooks and CI are the same for code from Claude or a person.
- **Conventions grow from corrections:** When something is corrected, it becomes a rule stated in `AGENTS.md`, so the correction is taken into account in later sessions. This can be applied either to my global conventions or the project-specific ones.


## Working with a Team

In addition to the automated checks above I insist on all code being reviewed. The most basic step is directing Claude to run a context-neutral review of its own code, and that generally generates some - often quite niche - findings. When working with other developers, I insist on at least one other human review; even if it is done with the help of AI, it is beneficial to have someone else review the findings and push back to me if necessary.

Another concern relevant when working in a team is sharing knowledge, and that falls into three main categories:

- Tests: In my mind, the purpose of tests is not (only) to validate execution of the code; they should also be written in such a way that a person reading them can get a relatively clear idea how the code interfaces work. This is especially important when making libraries, but even for projects like this one it can be helpful to other developers.
- Documentation: Every project should include a folder with various documentation on how to use it, what is the architecture and other human-oriented topics. It should be maintained alongside the code, following the functionalities as they are added.
- Coding agent configurations: When I work alone, or in a very small team, I often keep files like `AGENTS.md` and `CLAUDE.md` local to my own environment. But on a larger team, especially if other developers also use coding agents, it is beneficial to share common coding conventions, architectural decision records and the like, so these files can be tracked in git and used (and modified) by the whole team.


## Closing Note

All of the above are guidelines, and nothing is set in stone. My personal list of conventions keeps growing and changing as I develop, and new ideas can update anything previously defined as necessary - both on the global level and for any particular project.

When working with other developers, these changes become part of the project changes themselves - so others can review them and push back if necessary.
