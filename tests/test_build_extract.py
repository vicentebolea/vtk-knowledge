"""Tests for vtk_knowledge.pipeline.extract (VTK-free parts)."""

import json

from vtk_knowledge.pipeline.extract import _parse_help_text, write_jsonl


class TestParseHelpText:
    def test_empty_input(self):
        result = _parse_help_text("")
        assert result["class_doc"] == ""
        assert result["structured_docs"] == {"sections": {}}

    def test_class_doc_captured_before_sections(self):
        text = """\
Help on class vtkActor in module vtkmodules.vtkRenderingCore:

class vtkActor(vtkProp3D)
 |  vtkActor documentation line one.
 |  Another line.
 |
 |  Methods defined here:
 |  GetBounds(self)
 |      Return bounds.
"""
        result = _parse_help_text(text)
        assert "vtkActor documentation line one" in result["class_doc"]
        assert "Help on class" not in result["class_doc"]

    def test_class_doc_ignores_help_header(self):
        text = """\
Help on class vtkFoo in module vtkmodules.vtkSomething:

class vtkFoo(vtkBase)
 |  Actual docstring here.
 |
 |  Methods defined here:
"""
        result = _parse_help_text(text)
        assert "Actual docstring here" in result["class_doc"]
        assert "Help on class" not in result["class_doc"]
        assert "class vtkFoo" not in result["class_doc"]

    def test_section_and_method_parsed(self):
        text = """\
 |  Methods defined here:
 |  GetOutput(self)
 |      GetOutput() -> vtkDataObject
 |
 |      Return the output dataset.
"""
        result = _parse_help_text(text)
        sections = result["structured_docs"]["sections"]
        assert "Methods defined here" in sections
        methods = sections["Methods defined here"]["methods"]
        assert "GetOutput" in methods

    def test_multiple_sections(self):
        text = """\
 |  Methods defined here:
 |  MethodA(self)
 |      MethodA() -> None
 |
 |  Static methods defined here:
 |  StaticB()
 |      StaticB() -> int
"""
        result = _parse_help_text(text)
        sections = result["structured_docs"]["sections"]
        assert "Methods defined here" in sections
        assert "Static methods defined here" in sections

    def test_multiple_methods_in_section(self):
        text = """\
 |  Methods defined here:
 |  Alpha(self)
 |      Alpha body.
 |  Beta(self)
 |      Beta body.
"""
        result = _parse_help_text(text)
        methods = result["structured_docs"]["sections"]["Methods defined here"]["methods"]
        assert "Alpha" in methods
        assert "Beta" in methods


class TestWriteJsonl:
    def test_write_and_read_back(self, tmp_path):
        records = [
            {"class_name": "vtkFoo", "module_name": "m", "vtk_version": "9.3.0"},
            {"class_name": "vtkBar", "module_name": "m", "vtk_version": "9.3.0"},
        ]
        out = tmp_path / "out.jsonl"
        write_jsonl(records, out)
        lines = out.read_text().splitlines()
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert parsed[0]["class_name"] == "vtkFoo"
        assert parsed[1]["class_name"] == "vtkBar"

    def test_creates_parent_dirs(self, tmp_path):
        out = tmp_path / "nested" / "dir" / "out.jsonl"
        write_jsonl([{"class_name": "vtkX", "module_name": "m"}], out)
        assert out.exists()

    def test_empty_records(self, tmp_path):
        out = tmp_path / "empty.jsonl"
        write_jsonl([], out)
        assert out.read_text() == ""


class TestDownloadCommand:
    def test_download_writes_jsonl(self, tmp_path):
        import io
        import json
        import tarfile
        from unittest.mock import MagicMock, patch

        from typer.testing import CliRunner

        from vtk_knowledge.pipeline.cli import app
        from vtk_knowledge.schema.records import VTKDocRecord

        content = VTKDocRecord(class_name="vtkFoo", module_name="m").model_dump_json().encode()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            info = tarfile.TarInfo(name="vtk-knowledge.jsonl")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        blob = buf.getvalue()

        responses = iter(
            [
                json.dumps({"token": "t"}).encode(),
                json.dumps({"layers": [{"digest": "sha256:x"}]}).encode(),
                blob,
            ]
        )

        def _open(req_or_url, **_kw):
            data = next(responses)
            cm = MagicMock()
            cm.__enter__ = lambda s: MagicMock(read=lambda: data)
            cm.__exit__ = MagicMock(return_value=False)
            return cm

        with patch("vtk_knowledge.artifact.fetcher.urllib.request.urlopen", side_effect=_open):
            result = CliRunner().invoke(app, ["download", "9.6.1", "--output-dir", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert (tmp_path / "vtk-knowledge-9.6.1.jsonl").exists()
        assert "Artifact written to" in result.output

    def test_download_error_exits_nonzero(self, tmp_path):
        from unittest.mock import patch

        from typer.testing import CliRunner

        from vtk_knowledge.pipeline.cli import app

        with patch(
            "vtk_knowledge.artifact.fetcher.fetch_from_ghcr",
            side_effect=RuntimeError("connection refused"),
        ):
            result = CliRunner().invoke(app, ["download", "9.6.1", "--output-dir", str(tmp_path)])

        assert result.exit_code != 0
