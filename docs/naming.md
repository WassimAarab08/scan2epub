# The name of the project

The project was named before the first line of code was written, so that the
name, the package on PyPI, the repository and the Docker image would all
agree from the start.

## The candidates

The availability of every candidate was checked on **PyPI**, **npm**, the
**GitHub** search API and **Docker Hub**.

| Candidate | PyPI | npm | GitHub | Docker Hub | Verdict |
| --- | --- | --- | --- | --- | --- |
| **`scan2epub`** | free | free | 6 repositories, 0–1 stars, unrelated | taken | **Chosen** |
| `epubsmith` | free | free | 0 repositories | free | Alternative |
| `ocrleaf` | free | free | 0 repositories | free | Alternative |

## The decision

`scan2epub` was chosen for four reasons.

1. **It is the name of the tool in the specification.** The command line of
   the project is `scan2epub convert libro.pdf -o libro.epub --ocr teleocr
   --llm ollama/qwen3`. The name, the examples of the README and the actual
   binary are the same word, which is what people remember.
2. **It is descriptive without being cryptic.** `scan` says what the input is,
   `epub` says what the output is. Somebody who searches for "convert scanned
   PDF to EPUB" finds it.
3. **It is short enough to type.** Two syllables, no confusion with any other
   tool of the ecosystem.
4. **The namespace is free.** `WassimAarab08/scan2epub` did not exist, the
   `scan2epub` package was not taken on PyPI, and the name was not taken on
   npm.

The six repositories with the same name on GitHub are unrelated hobby
projects with 0 or 1 stars, and none of them uses the name as a trademark.
The Docker Hub namespace is taken by an unrelated user, which is why the
images are published on **GHCR** (`ghcr.io/wassimaarab08/scan2epub`) instead:
GHCR is free, has no pull limit and is tied to the repository.

## The identifiers

| Resource | Name |
| --- | --- |
| Repository | `github.com/WassimAarab08/scan2epub` |
| Python package | `scan2epub` on PyPI |
| The command | `scan2epub` |
| The container image | `ghcr.io/wassimaarab08/scan2epub` |
| The configuration file | `config.toml` in `~/.config/scan2epub/` |
| The cache | `~/.cache/scan2epub/` |
| The environment prefix | `SCAN2EPUB_` |
| The import package | `scan2epub` |

## Changing the name

The name is settled until the v0.1.0 release. After that, the PyPI package and
the Docker images keep the old name, and only the repository and the
documentation change. Renaming before the first release is free; renaming
afterwards is not.
