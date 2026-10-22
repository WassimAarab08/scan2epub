"""Tests for the PaddleOCR-VL, TeleOCR and Kraken adapters.

None of these tests needs a model, a GPU or a network: they check the
contract of the adapters, the safety of the TeleOCR adapter, the laziness of
the imports and the parsing of the results.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from scan2epub.domain.models import BlockKind, PageImage
from scan2epub.domain.ports import OcrEngine
from scan2epub.errors import EngineNotAvailableError, OcrError
from scan2epub.infrastructure.ocr import kraken as kraken_module
from scan2epub.infrastructure.ocr.kraken import KrakenOcrEngine
from scan2epub.infrastructure.ocr.paddleocr_vl import PaddleOcrVlEngine, _parse_markdown
from scan2epub.infrastructure.ocr.teleocr import TeleOcrEngine
from scan2epub.infrastructure.ocr.teleocr import _parse_markdown as _tele_parse

#: The root of the repository, used to run the subprocesses.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: The adapters that must not pull in PyTorch when they are imported.
LAZY_MODULES = (
    "scan2epub.infrastructure.ocr.paddleocr_vl",
    "scan2epub.infrastructure.ocr.teleocr",
    "scan2epub.infrastructure.ocr.kraken",
)

#: The Markdown that the fake models write.
MARKDOWN = "# Chapter one\n\nThe text of\nthe page."


class _FakeTensor:
    """A tensor with a shape and a slicing."""

    def __init__(self, rows: list[list[int]]) -> None:
        """Store the rows of the tensor."""
        self.rows = rows

    @property
    def shape(self) -> tuple[int, int]:
        """Return the shape of the tensor."""
        return (len(self.rows), len(self.rows[0]))

    def __getitem__(self, key: tuple[slice, slice]) -> _FakeTensor:
        """Return the rows of the slice."""
        return _FakeTensor([row[key[1]] for row in self.rows[key[0]]])


class _FakeProcessor:
    """A processor that prepares the tensors of a fake model."""

    def apply_chat_template(self, messages: object, **kwargs: object) -> dict[str, _FakeTensor]:
        """Return the tensors of the page."""
        return {"input_ids": _FakeTensor([[1, 2, 3]])}

    def batch_decode(self, sequences: object, **kwargs: object) -> list[str]:
        """Return the Markdown of the page."""
        return [MARKDOWN]


class _FakeModel:
    """A model that generates the tokens of the page."""

    def generate(self, **kwargs: object) -> _FakeTensor:
        """Return the tokens of the page."""
        return _FakeTensor([[1, 2, 3, 4, 5]])


class _BrokenModel:
    """A model that fails on every page."""

    def generate(self, **kwargs: object) -> _FakeTensor:
        """Fail on every page."""
        raise RuntimeError("the model is broken")


def _page(tmp_path: Path, index: int = 0) -> PageImage:
    """Return a page that does not need to exist on disk."""
    return PageImage(index=index, path=tmp_path / "page.png", width=1000, height=2000)


def _real_page(tmp_path: Path, index: int = 0) -> PageImage:
    """Return a page that is written on disk."""
    page = _page(tmp_path, index)
    Image.new("L", (page.width, page.height), "white").save(page.path)
    return page


def test_the_paddleocr_engine_satisfies_the_ocr_port() -> None:
    """The engine implements the port of the application layer."""
    assert isinstance(PaddleOcrVlEngine(), OcrEngine)


def test_the_teleocr_engine_satisfies_the_ocr_port() -> None:
    """The engine implements the port of the application layer."""
    assert isinstance(TeleOcrEngine(trust_remote_code=True), OcrEngine)


def test_the_kraken_engine_satisfies_the_ocr_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """The engine implements the port of the application layer."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    assert isinstance(KrakenOcrEngine(), OcrEngine)


def test_the_paddleocr_engine_describes_its_settings() -> None:
    """The settings that change the result are described."""
    engine = PaddleOcrVlEngine(device="cpu", max_new_tokens=128, revision="abc123")
    assert engine.describe() == {
        "engine": "paddleocr-vl",
        "model": "PaddlePaddle/PaddleOCR-VL",
        "device": "cpu",
        "max_new_tokens": 128,
        "revision": "abc123",
    }


def test_the_teleocr_engine_describes_its_settings() -> None:
    """The settings that change the result are described."""
    engine = TeleOcrEngine(trust_remote_code=True, device="cpu")
    assert engine.describe() == {
        "engine": "teleocr",
        "model": "XingChen-AGI/TeleOCR",
        "device": "cpu",
        "revision": "true",
        "trust_remote_code": True,
    }


def test_the_kraken_engine_describes_its_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The settings that change the result are described."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    engine = KrakenOcrEngine(model="my-model.mlmodel", binary="kraken")
    assert engine.describe() == {
        "engine": "kraken",
        "model": "my-model.mlmodel",
        "binary": "kraken",
    }


def test_teleocr_refuses_to_run_without_trusted_remote_code() -> None:
    """The engine refuses to run the code of the model repository."""
    with pytest.raises(EngineNotAvailableError) as error:
        TeleOcrEngine()
    assert "trust_remote_code" in str(error.value)


def test_teleocr_runs_when_the_remote_code_is_trusted() -> None:
    """The engine accepts an explicit trust of the model repository."""
    engine = TeleOcrEngine(trust_remote_code=True)
    assert engine.name == "teleocr"
    assert engine.trust_remote_code is True


def test_teleocr_refuses_a_moving_revision() -> None:
    """The engine never loads the moving branch of the repository."""
    with pytest.raises(EngineNotAvailableError) as error:
        TeleOcrEngine(trust_remote_code=True, revision="main")
    assert "pinned" in str(error.value)


def test_kraken_reports_a_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    """A clear error is raised when Kraken is not installed."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: None)
    with pytest.raises(EngineNotAvailableError) as error:
        KrakenOcrEngine()
    assert "pip install kraken" in str(error.value)


def test_kraken_reports_a_missing_binary_when_it_reads(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The binary is looked up again for every page."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    engine = KrakenOcrEngine()
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: None)
    with pytest.raises(EngineNotAvailableError):
        engine.recognize(_page(tmp_path))


@pytest.mark.parametrize("module", LAZY_MODULES)
def test_importing_an_adapter_does_not_import_torch(module: str) -> None:
    """Importing an adapter never pulls in PyTorch."""
    code = f"import sys, {module}; assert 'torch' not in sys.modules"
    completed = subprocess.run(  # noqa: S603 - a fixed argument list, never a shell
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        cwd=PROJECT_ROOT,
    )
    assert completed.returncode == 0, completed.stderr


def test_the_paddleocr_engine_reports_a_missing_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A model that cannot be loaded is reported clearly."""
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "transformers", None)
    engine = PaddleOcrVlEngine(model="scan2epub/does-not-exist")
    with pytest.raises(EngineNotAvailableError) as error:
        engine.recognize(_page(tmp_path))
    assert "scan2epub[vlm]" in str(error.value)


def test_the_teleocr_engine_reports_a_missing_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A model that cannot be loaded is reported clearly."""
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "transformers", None)
    engine = TeleOcrEngine(trust_remote_code=True)
    with pytest.raises(EngineNotAvailableError):
        engine.recognize(_page(tmp_path))


def test_the_markdown_becomes_one_block_per_paragraph(tmp_path: Path) -> None:
    """The paragraphs of the Markdown keep their physical lines."""
    markdown = "# Chapter one\n\nThe first line\nof the paragraph.\n\nThe second one."
    paragraphs = _parse_markdown(markdown)
    assert [paragraph.lines for paragraph in paragraphs] == [
        ("Chapter one",),
        ("The first line", "of the paragraph."),
        ("The second one.",),
    ]
    assert paragraphs[0].level == 1
    assert paragraphs[1].level == 0


def test_the_markdown_markup_is_removed() -> None:
    """The markup of the Markdown is not part of the text."""
    markdown = "A **bold** word, an *italic* one and a [link](https://example.org)."
    paragraphs = _parse_markdown(markdown)
    assert paragraphs[0].lines == ("A bold word, an italic one and a link.",)


def test_the_lists_of_the_markdown_become_their_own_blocks() -> None:
    """Every item of a list is a block of its own."""
    paragraphs = _parse_markdown("- first\n- second")
    assert [paragraph.lines for paragraph in paragraphs] == [("first",), ("second",)]


def test_the_blocks_are_placed_on_the_page(tmp_path: Path) -> None:
    """The blocks of the page are laid out from the top to the bottom."""
    engine = PaddleOcrVlEngine()
    page = _page(tmp_path)
    blocks = engine._layout(_parse_markdown("one\ntwo\n\nthree"), page)
    assert len(blocks) == 2
    assert blocks[0].lines == ("one", "two")
    assert blocks[0].bbox.y0 < blocks[1].bbox.y0
    assert blocks[0].bbox.y1 <= blocks[1].bbox.y0
    assert blocks[0].page == page.index
    assert blocks[0].order == 0


def test_the_headings_of_the_markdown_are_marked_as_headings(tmp_path: Path) -> None:
    """A heading of the Markdown becomes a heading of the page."""
    engine = PaddleOcrVlEngine()
    blocks = engine._layout(_parse_markdown("## Chapter one"), _page(tmp_path))
    assert blocks[0].kind is BlockKind.HEADING
    assert blocks[0].level == 2


def test_the_markdown_of_teleocr_becomes_one_block_per_paragraph() -> None:
    """The paragraphs of the Markdown keep their physical lines."""
    paragraphs = _tele_parse("# Chapter one\n\nThe first line\nof the paragraph.")
    assert [paragraph.lines for paragraph in paragraphs] == [
        ("Chapter one",),
        ("The first line", "of the paragraph."),
    ]
    assert paragraphs[0].level == 1


def test_the_paddleocr_engine_reads_the_markdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Markdown of the model becomes the blocks of the page."""
    engine = PaddleOcrVlEngine()
    monkeypatch.setattr(engine, "_load", lambda: (_FakeProcessor(), _FakeModel()))
    page = _real_page(tmp_path)
    blocks = engine.recognize(page)
    assert [block.lines for block in blocks] == [
        ("Chapter one",),
        ("The text of", "the page."),
    ]
    assert blocks[0].kind is BlockKind.HEADING
    assert blocks[0].page == page.index
    assert blocks[0].order == 0


def test_the_teleocr_engine_reads_the_markdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Markdown of the model becomes the blocks of the page."""
    engine = TeleOcrEngine(trust_remote_code=True)
    monkeypatch.setattr(engine, "_load", lambda: (_FakeProcessor(), _FakeModel()))
    page = _real_page(tmp_path)
    blocks = engine.recognize(page)
    assert [block.lines for block in blocks] == [
        ("Chapter one",),
        ("The text of", "the page."),
    ]
    assert blocks[1].page == page.index


def test_the_paddleocr_engine_reports_a_broken_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A page that cannot be read is an error."""
    engine = PaddleOcrVlEngine()
    monkeypatch.setattr(engine, "_load", lambda: (_FakeProcessor(), _FakeModel()))
    with pytest.raises(OcrError):
        engine.recognize(_page(tmp_path))


def test_the_paddleocr_engine_reports_a_broken_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A model that fails on the page is an error."""
    engine = PaddleOcrVlEngine()
    monkeypatch.setattr(engine, "_load", lambda: (_FakeProcessor(), _BrokenModel()))
    with pytest.raises(OcrError):
        engine.recognize(_real_page(tmp_path))


def test_the_teleocr_engine_reports_a_broken_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A model that fails on the page is an error."""
    engine = TeleOcrEngine(trust_remote_code=True)
    monkeypatch.setattr(engine, "_load", lambda: (_FakeProcessor(), _BrokenModel()))
    with pytest.raises(OcrError):
        engine.recognize(_real_page(tmp_path))


def _alto() -> str:
    """Return an ALTO document with two lines."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <Layout>
    <Page WIDTH="1000" HEIGHT="2000" PHYSICAL_IMG_NR="0">
      <PrintSpace HPOS="0" VPOS="0" WIDTH="1000" HEIGHT="2000">
        <TextBlock ID="TB1" HPOS="100" VPOS="200" WIDTH="500" HEIGHT="40">
          <TextLine ID="TL1" HPOS="100" VPOS="200" WIDTH="500" HEIGHT="40">
            <String ID="S1" CONTENT="Hola" WC="0.9"/>
            <String ID="S2" CONTENT="mundo" WC="0.7"/>
          </TextLine>
        </TextBlock>
        <TextBlock ID="TB2" HPOS="100" VPOS="300" WIDTH="500" HEIGHT="40">
          <TextLine ID="TL2" HPOS="100" VPOS="300" WIDTH="500" HEIGHT="40">
            <String ID="S3" CONTENT="Adios" WC="0.8"/>
          </TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>
"""


def test_the_alto_of_kraken_becomes_one_block_per_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Every line of the ALTO document is a text block."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    engine = KrakenOcrEngine()
    result = tmp_path / "page.xml"
    result.write_text(_alto(), encoding="utf-8")
    page = _page(tmp_path)
    blocks = engine._to_blocks(result, page)
    assert [block.lines for block in blocks] == [("Hola mundo",), ("Adios",)]
    assert [block.order for block in blocks] == [0, 1]
    assert all(block.page == page.index for block in blocks)


def test_the_geometry_of_kraken_is_normalised(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The box of a line is relative to the page."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    engine = KrakenOcrEngine()
    result = tmp_path / "page.xml"
    result.write_text(_alto(), encoding="utf-8")
    page = _page(tmp_path)
    blocks = engine._to_blocks(result, page)
    assert blocks[0].bbox.x0 == pytest.approx(0.1)
    assert blocks[0].bbox.y0 == pytest.approx(0.1)
    assert blocks[0].bbox.x1 == pytest.approx(0.6)
    assert blocks[0].bbox.y1 == pytest.approx(0.12)


def test_the_confidence_of_kraken_is_the_mean_of_its_words(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The confidence of a line is the mean of the confidence of its words."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    engine = KrakenOcrEngine()
    result = tmp_path / "page.xml"
    result.write_text(_alto(), encoding="utf-8")
    blocks = engine._to_blocks(result, _page(tmp_path))
    assert blocks[0].confidence == pytest.approx(0.8)
    assert blocks[1].confidence == pytest.approx(0.8)


def test_kraken_calls_the_program_with_an_argument_list(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The program is called with an argument list and never through a shell."""
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Record the call and return an empty result."""
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    monkeypatch.setattr(kraken_module.subprocess, "run", fake_run)
    page = _page(tmp_path)
    Image.new("L", (page.width, page.height), "white").save(page.path)
    engine = KrakenOcrEngine(model="my-model")
    with pytest.raises(OcrError):
        # The fake program writes no result, so the ALTO file is missing.
        engine.recognize(page)
    assert len(calls) == 1
    command = calls[0]
    assert command[0] == "/usr/bin/kraken"
    assert command[command.index("-i") + 1].endswith(".tif")
    assert command[command.index("-m") + 1] == "my-model"


def test_kraken_reports_a_broken_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A page that cannot be read is an error."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    engine = KrakenOcrEngine()
    with pytest.raises(OcrError):
        engine.recognize(_page(tmp_path))


def test_kraken_reports_a_failed_program(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A program that fails is an error."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    monkeypatch.setattr(
        kraken_module.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, "", "it broke"),
    )
    engine = KrakenOcrEngine()
    with pytest.raises(OcrError) as error:
        engine.recognize(_real_page(tmp_path))
    assert "it broke" in str(error.value)


def test_kraken_reports_a_program_that_is_too_slow(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A program that takes too long is an error."""

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        """Fail as a program that timed out."""
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    monkeypatch.setattr(kraken_module.subprocess, "run", fake_run)
    engine = KrakenOcrEngine(timeout=1)
    with pytest.raises(OcrError):
        engine.recognize(_real_page(tmp_path))


def test_kraken_reports_an_unreadable_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A result that is not an ALTO document is an error."""
    monkeypatch.setattr(kraken_module.shutil, "which", lambda name: "/usr/bin/kraken")
    engine = KrakenOcrEngine()
    result = tmp_path / "page.xml"
    result.write_text("this is not xml", encoding="utf-8")
    with pytest.raises(OcrError):
        engine._to_blocks(result, _page(tmp_path))
