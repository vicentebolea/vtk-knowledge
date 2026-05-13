"""Tests for vtk_knowledge.build.extract (VTK-free parts)."""

import json

from vtk_knowledge.build.extract import _parse_help_text, write_jsonl


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
