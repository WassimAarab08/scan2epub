# Contributing to scan2epub

Thanks for taking the time to contribute! This document explains how to set up a
development environment, the conventions we follow, and the rules that keep the
project safe (permissive licenses only).

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

## Table of contents

- [The branching model](#the-branching-model)
- [Licensing rules (read this first)](#licensing-rules-read-this-first)
- [Development setup](#development-setup)
- [Quality gates](#quality-gates)
- [Commit conventions](#commit-conventions)
- [Pull request process](#pull-request-process)
- [Adding an OCR engine or text corrector](#adding-an-ocr-engine-or-text-corrector)
- [Adding a dependency](#adding-a-dependency)
- [Code style](#code-style)
- [Reporting bugs](#reporting-bugs)
- [Releases](#releases)

## The branching model

The project uses **trunk-based development** with a single long-lived branch.

| Branch | What it holds | Who writes to it |
| --- | --- | --- |
| `main` | The code that is released. It is **always** in a working state. | Nobody directly: it is written by the merge of a pull request. |
| `feat/…`, `fix/…`, `docs/…`, `chore/…` | One pull request each. | You, from your fork or from a branch of this repository. |

The rules:

1. **Never push to `main`.** `main` is protected: a direct push is refused,
   for everybody, including the maintainers.
2. **Every change goes through a pull request**, however small it is. A
   one-line typo fix is a pull request too.
3. **The CI must be green** before a pull request can be merged. The checks
   that gate the merge are `quality` (lint, types, tests), `epub` (the
   generated book passes EPUBCheck) and `browser` (the book renders in a real
   browser and opens in foliate-js). They must also be **up to date with
   `main`**: rebase and the CI runs again.
4. **The history is linear.** The maintainers squash-merge, with the title of
   the pull request, which is a Conventional Commit.
5. **Every commit is signed off.** Add the `Signed-off-by` line with
   `git commit -s`, or with the "certify the origin" checkbox of the GitHub
   web editor. It is the [Developer Certificate of Origin](https://developercertificate.org/).
6. **Do not force-push a branch that has a review in progress.** Use
   `git push --force-with-lease` on your own branch.
7. **The conversation must be resolved** before the merge: every comment of
   the review has to be answered.

### About the review

A review is **requested** on every pull request — the `CODEOWNERS` file names
who reviews which area, and the pull request template has a checklist — but it
is not **required** by the branch protection yet, because the project has only
one maintainer and a pull request cannot be approved by its own author.

As soon as there is a second maintainer, the protection will require one
approving review, and this paragraph will be updated. In the meantime, a
pull request that touches an unfamiliar area is better reviewed by somebody
before it is merged: say so in the pull request, and the maintainer will wait
for it.

### Naming the branches

```
feat/ocr-paddleocr-vl      a new engine
feat/api-job-queue         a new feature
fix/cache-language-key     a bug
docs/adding-an-engine      the documentation
chore/dependabot           the maintenance
```

The name is the type of the change, a slash, and a short description in
kebab case.

### Working on a pull request

```bash
git clone https://github.com/<your-name>/scan2epub.git
cd scan2epub
git remote add upstream https://github.com/WassimAarab08/scan2epub.git
git checkout -b fix/whatever-the-problem-is
# … your changes …
git commit -s -m "fix(ocr): whatever the change is"
git push -u origin fix/whatever-the-problem-is
```

The `-s` adds the `Signed-off-by` line that the project requires. The
repository also carries a [`.gitmessage`](.gitmessage) template that explains
it, and GitHub shows it in the web editor.

Then open the pull request against `main` from the GitHub page, or:

```bash
gh pr create --base main --fill
```

Keep the branch up to date with `main` while you work:

```bash
git fetch upstream
git rebase upstream/main
```

### Working on a small issue

If the issue is labelled `good first issue`, comment on it before you start,
so that two people do not work on the same thing. If somebody already did,
the comment will tell you.

## Licensing rules (read this first)

`scan2epub` is licensed under **Apache-2.0**. To keep it usable inside
libraries, universities and commercial products, **every** dependency must be
permissive.

**Forbidden:** GPL, AGPL, LGPL-only, SSPL, BUSL, Commons Clause, and any
non-commercial or source-available license — including transitive dependencies
of the packages you add.

Known offenders that must never be added (they are explicitly rejected):

| Package | License |
| --- | --- |
| PyMuPDF / `fitz` | AGPL-3.0 |
| EbookLib | AGPL-3.0 |
| `marker`, `surya` | GPL-3.0 |
| MinerU (non-Pro / community editions) | AGPL-3.0 / non-commercial |

**Before opening a PR that adds a dependency:**

1. Check the license of the package *and* of its runtime dependencies.
2. Add a row to [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
3. Run `uv run python scripts/check_licenses.py` — CI will fail otherwise.
4. Prefer an extra (`[project.optional-dependencies]`) over a hard dependency
   whenever the feature is not needed by every user.

Model weights are **never** vendored into the repository. Reference them by
Hugging Face repository id and document their license in
`THIRD_PARTY_LICENSES.md`.

## Development setup

Requirements: Python 3.12+, [`uv`](https://docs.astral.sh/uv/), Git.
Optionally: the `tesseract` binary for the default OCR engine, Node 20+ and
Docker for the web UI and container builds.

```bash
git clone https://github.com/WassimAarab08/scan2epub.git
cd scan2epub

uv sync --all-extras        # install everything, including dev tools
uv run scan2epub --help     # verify the CLI works

# Optional engines
uv sync --extra vlm         # TeleOCR / PaddleOCR-VL (torch + transformers)
uv sync --extra llm         # LiteLLM remote OCR + correction
```

Run the web UI:

```bash
cd web
npm install
npm start                   # http://localhost:4200, proxies to the API
```

## Quality gates

Everything below must pass before a pull request can be merged. The same
commands run in CI.

```bash
uv run ruff format --check .      # formatting
uv run ruff check .               # lint
uv run pyright                    # strict type checking
uv run pytest --cov=src/scan2epub --cov-report=term-missing
uv run python scripts/check_licenses.py   # no copyleft dependency
```

Type annotations are required and `pyright` runs in **strict** mode. Public
functions and methods need docstrings in the imperative mood ("Return the
...", not "Returns the ...").

Coverage must stay at or above **80 %** for `src/scan2epub/domain` and
`src/scan2epub/application`. New code without tests will fail CI.

### The browser tests

The browser tests open the generated book in a real browser and in
**foliate-js**, the reference EPUB 3 reader. They are the strongest proof that
the output is a real book and not a ZIP file with some XML inside.

```bash
uv run playwright install chromium              # once
uv run python scripts/fetch_browser_assets.py   # once: installs foliate-js
uv run pytest tests/browser -v
```

They are skipped, not failed, when the browser is not installed. The full
guide is in [`docs/testing.md`](docs/testing.md).

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```
<type>(<scope>): <imperative summary>

<optional body>

<optional footer>
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
`build`, `ci`, `chore`, `revert`.

Scopes: `cli`, `api`, `web`, `core`, `ocr`, `correct`, `epub`, `cache`, `eval`,
`docs`, `deps`.

Examples:

```
feat(correct): add normalized edit-distance guardrail
fix(epub): write mimetype as the first uncompressed ZIP entry
docs(readme): add the before/after comparison
test(clean): cover hyphen re-joining across page boundaries
```

Every commit must also carry the sign-off line:

```
Signed-off-by: Your Name <you@example.com>
```

Use `git commit -s` to add it. It is the same as ticking "certify the origin"
in the GitHub web editor, and it is what the
[Developer Certificate of Origin](https://developercertificate.org/) asks for.

Keep commits small and atomic. A commit should build and pass the gates on its
own.

## Pull request process

1. Open an issue first for anything bigger than a bug fix, so that the
   approach can be discussed before you write the code.
2. Create a branch from `main` and make your change, with tests.
3. Run the quality gates locally.
4. Push the branch and open a pull request against `main`, using the
   template. Describe **why** the change is needed, not only what it does.
5. A maintainer reviews it within a few days. Expect questions — that is
   normal, and it is not a sign that the change is bad.
6. When the review is done and the CI is green, the maintainer squash-merges
   it with a Conventional Commit title.

A pull request is ready to be reviewed when:

- [ ] It is based on `main` and it can be merged without a conflict.
- [ ] The quality gates pass locally.
- [ ] The new behaviour is covered by tests.
- [ ] The documentation is updated when the behaviour changes.
- [ ] `CHANGELOG.md` has an entry under `## [Unreleased]`.
- [ ] It adds no copyleft dependency.

The title of the pull request must be a Conventional Commit, because it
becomes the title of the commit:

```
fix(clean): stop treating a sentence that starts with "Book" as a heading
feat(ocr): add the PaddleOCR-VL engine
docs: document the cost control
```

## Releases

The releases follow [Semantic Versioning](https://semver.org/):

| Change | Version |
| --- | --- |
| A bug fix | `PATCH` |
| A new feature, backwards compatible | `MINOR` |
| A change that breaks the API or the format | `MAJOR` |

The maintainers cut the releases. The `release.yml` workflow publishes the
container images and creates the GitHub release from the `CHANGELOG.md`, so
the only thing a contributor has to do is to add their entry under
`## [Unreleased]`.

## Adding an OCR engine or text corrector

Engines and correctors are **ports** (protocols) with pluggable adapters. The
whole guide fits in under 50 lines; see
[`docs/adding-an-engine.md`](docs/adding-an-engine.md).

In short:

```python
from scan2epub.domain.ports import OcrEngine
from scan2epub.domain.models import Page, TextBlock


class MyEngine:
    name = "my-engine"

    def recognize(self, page: Page) -> list[TextBlock]:
        ...
        return [TextBlock(text="...", bbox=(0, 0, 1, 1), confidence=0.9)]
```

Register it in `config.toml`:

```toml
[ocr.my-engine]
adapter = "scan2epub.infrastructure.ocr.my_engine:MyEngine"
```

## Adding a dependency

```bash
uv add <package>            # runtime
uv add --optional <pkg>    # extra
uv sync && uv run python scripts/check_licenses.py
```

Then update `THIRD_PARTY_LICENSES.md` in the same commit.

## Code style

- **English** for code, comments, docstrings, commit messages and
  documentation. User-facing CLI help may be English; translations live in the
  docs.
- Four-space indentation, 100-column lines (configured in `pyproject.toml`).
- `ruff format` is the single source of truth for formatting. Do not hand-tune.
- Prefer explicit types over `Any`. `pyright` strict mode forbids implicit
  `Any` leaks.
- Public API changes need a `CHANGELOG.md` entry under `## [Unreleased]`.

## Reporting bugs

Open an issue using the **Bug report** template. A good report includes:

- The exact command you ran and the full output.
- `scan2epub doctor` output (it prints versions, available engines and config).
- The input: page count, whether the PDF is text-based or scanned, and — if
  possible — a few sample pages.
- The expected vs. actual result.

If the issue involves copyrighted material, **do not attach it**. Use a
public-domain sample from [`samples/`](samples/) or a self-made synthetic page.

## Code of Conduct

Instances of unacceptable behaviour should be reported to the maintainers at
`conduct@scan2epub.org` (or the address in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)).
All reports will be reviewed and handled promptly and discreetly.
