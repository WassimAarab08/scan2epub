# Third-Party Licenses

`scan2epub` is licensed under the [Apache License 2.0](LICENSE).

This project deliberately avoids GPL / AGPL / copyleft dependencies so that the
tool can be embedded in libraries, commercial services and institutional
infrastructure without additional obligations.

Every runtime and development dependency is listed below with the license that
applies to the **Python / JavaScript packaging** we consume. Licenses of
optional system binaries (Tesseract, Java/EPUBCheck) and of downloaded model
weights are tracked separately, at the bottom of this file.

> This file is maintained by hand. Any dependency change must be accompanied by
> a commit that updates this table (see `CONTRIBUTING.md`).

## Runtime dependencies — Python

| Package | Version | License | Used for |
| --- | --- | --- | --- |
| [pypdfium2](https://github.com/pypdfium2-team/pypdfium2) | >=5.14 | BSD-3-Clause OR Apache-2.0 | PDF rasterisation (PDFium, BSD-3-Clause) |
| [opencv-python-headless](https://github.com/opencv/opencv-python) | >=5.0 | Apache-2.0 (wrapper: MIT) | Deskew, binarisation, denoise, border crop |
| [numpy](https://github.com/numpy/numpy) | >=2.0 | BSD-3-Clause | Array primitives |
| [pillow](https://github.com/python-pillow/Pillow) | >=11.0 | MIT-CMU | Image I/O |
| [pytesseract](https://github.com/mhammond/pytesseract) | >=0.3.13 | Apache-2.0 | Tesseract OCR bindings |
| [pydantic](https://github.com/pydantic/pydantic) | >=2.10 | MIT | Data models / settings |
| [pydantic-settings](https://github.com/pydantic/pydantic-settings) | >=2.6 | MIT | Environment-variable configuration |
| [fastapi](https://github.com/fastapi/fastapi) | >=0.115 | MIT | REST API |
| [uvicorn](https://github.com/encode/uvicorn) | >=0.32 | BSD-3-Clause | ASGI server |
| [typer](https://github.com/fastapi/typer) | >=0.12 | MIT | CLI |
| [rich](https://github.com/Textualize/rich) | >=13.7 | MIT | Terminal progress bars / reports |
| [structlog](https://github.com/hynek/structlog) | >=24.1 | MIT | Structured logging |
| [httpx](https://github.com/encode/httpx) | >=0.27 | BSD-3-Clause | HTTP client (SSE, remote APIs) |
| [tenacity](https://github.com/jd/tenacity) | >=9.0 | Apache-2.0 | Retries with exponential backoff |
| [tomli-w](https://github.com/scientific-python/tomli-w) | >=1.1 | MIT | Writing `config.toml` |
| [certifi](https://github.com/certifi/python-certifi) | >=2024.2 | **MPL-2.0** | Root certificates, pulled in by `httpx` |

> **Note on `certifi`.** MPL-2.0 is a *file-level* copyleft licence: it does
> not impose any obligation on the work that merely uses the package, and it
> is on the OSI approved list. It is tracked here for transparency.

## Runtime dependencies — Python (optional extras)

| Package | Extra | Version | License | Used for |
| --- | --- | --- | --- | --- |
| [litellm](https://github.com/BerriAI/litellm) | `llm` | >=1.60 | MIT | Remote VLM OCR and LLM text correction |
| [transformers](https://github.com/huggingface/transformers) | `vlm` | >=5.0 | Apache-2.0 | TeleOCR / PaddleOCR-VL inference |
| [torch](https://github.com/pytorch/pytorch) | `vlm` | >=2.6 | BSD-3-Clause | Tensor runtime for local VLMs |
| [accelerate](https://github.com/huggingface/accelerate) | `vlm` | >=1.0 | Apache-2.0 | Model loading helpers |
| [sentencepiece](https://github.com/google/sentencepiece) | `vlm` | >=0.2 | Apache-2.0 | PaddleOCR-VL tokenizer |
| [vllm](https://github.com/vllm-project/vllm) | `gpu` | >=0.8 | Apache-2.0 | High-throughput VLM serving |
| [jiwer](https://github.com/jitsi/jiwer) | `eval` | >=4.0 | MIT | CER / WER metrics |

## Development dependencies

| Package | Version | License | Used for |
| --- | --- | --- | --- |
| [pytest](https://github.com/pytest-dev/pytest) | >=8.3 | MIT | Test runner |
| [pytest-cov](https://github.com/pytest-dev/pytest-cov) | >=6.0 | MIT | Coverage |
| [ruff](https://github.com/astral-sh/ruff) | >=0.8 | MIT | Lint + format |
| [pyright](https://github.com/microsoft/pyright) | >=1.1.390 | MIT | Static type checking (strict) |
| [respx](https://github.com/lundberg/respx) | >=0.22 | MIT | HTTP mocking in tests |
| [freezegun](https://github.com/spulec/freezegun) | >=1.5 | Apache-2.0 | Deterministic time in tests |

## Frontend dependencies

| Package | Version | License | Used for |
| --- | --- | --- | --- |
| [@angular/core](https://angular.dev) | >=20 | MIT | Web UI |
| [tailwindcss](https://github.com/tailwindlabs/tailwindcss) | >=4 | MIT | Styling |
| [foliate-js](https://github.com/johnfactotum/foliate-js) | 1.0.1 (pinned) | MIT | In-browser EPUB 3 renderer |
| [zip.js](https://github.com/gildas-lormeau/zip.js) (vendored by foliate-js) | — | BSD-3-Clause | ZIP reader |
| [fflate](https://github.com/101arrowz/fflate) (vendored by foliate-js) | — | MIT | DEFLATE |

## System binaries (not Python dependencies)

| Component | License | Notes |
| --- | --- | --- |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | Apache-2.0 | Default local OCR engine; `tesseract` CLI + `tessdata` |
| [EPUBCheck](https://github.com/w3c/epubcheck) | BSD-3-Clause | EPUB 3 conformance validation (CI + `--validate`) |
| [Eclipse Temurin JRE](https://adoptium.net/) | GPL-2.0 with Classpath Exception | Required to run EPUBCheck; invoked as a separate process, never linked |
| [Kraken](https://github.com/mittagessen/kraken) | Apache-2.0 | Optional historical HTR engine (planned adapter) |
| [Ollama](https://github.com/ollama/ollama) | MIT | Optional local LLM server |

> **Note on Temurin.** The JRE is used strictly as an external executable to run
> EPUBCheck. It is not linked into `scan2epub` and is not distributed in the
> Python wheel. The Classpath Exception makes it safe to invoke from an
> Apache-2.0 project.

## Model weights (downloaded on demand, never vendored)

| Model | Repository | License | Notes |
| --- | --- | --- | --- |
| TeleOCR | [`XingChen-AGI/TeleOCR`](https://huggingface.co/XingChen-AGI/TeleOCR) | Apache-2.0 | ~1.2B, Qwen2.5-VL based, requires `trust_remote_code` |
| PaddleOCR-VL | [`PaddlePaddle/PaddleOCR-VL`](https://huggingface.co/PaddlePaddle/PaddleOCR-VL) | Apache-2.0 | 0.9B, natively supported by `transformers` |
| Tesseract language data | [`tessdata`](https://github.com/tesseract-ocr/tessdata) | Apache-2.0 | `spa`, `spa_old`, `eng`, `fra`, `deu`… |
| Kraken models | [Zenodo OCR models](https://zenodo.org/communities/ocr_models) | **Per-model** | Verify the license of each model before use |

Model weights are downloaded lazily into the Hugging Face cache
(`HF_HOME`, default `~/.cache/huggingface`) and are **never** committed to this
repository. The `.gitignore` blocks `*.safetensors`, `*.bin`, `*.onnx`,
`*.mlmodel` and the `models/` directory.

## Explicitly rejected dependencies

| Package | License | Why rejected |
| --- | --- | --- |
| PyMuPDF (`fitz`) | AGPL-3.0 | Copyleft; forces the whole stack to AGPL |
| EbookLib | AGPL-3.0 | Copyleft; also does not target EPUB 3 navigation well |
| `marker` / `surya` | GPL-3.0 | Copyleft |
| MinerU (non-commercial edition) | AGPL-3.0 / non-commercial | Copyleft + non-commercial restriction |
| `python-slugify` | BSD-3-Clause | Permissive itself, but it pulls in `text-unidecode`, which is **GPL/Artistic**. Removed for that reason. |
| `paddleocr` runtime | Apache-2.0 (ok) but heavyweight | Not used; we rely on `transformers` for PaddleOCR-VL |
| `kraken` (as a hard dependency) | Apache-2.0 (ok) | Pulls a large scientific stack; kept as an optional adapter |

## Verification

The dependency license table above is enforced in CI by
`scripts/check_licenses.py`, which reads the installed distribution metadata and
fails the build if any dependency declares a copyleft or proprietary license.
