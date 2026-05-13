"""Tests for vtk_knowledge.schema.records."""

import json
from hashlib import sha1

import pytest

from vtk_knowledge.schema.records import (
    SCHEMA_VERSION,
    VTKDocRecord,
    VTKMethod,
    VTKRole,
)


class TestVTKRole:
    def test_all_expected_values(self):
        values = {r.value for r in VTKRole}
        assert "source" in values
        assert "filter" in values
        assert "unknown" in values

    def test_is_string_enum(self):
        assert VTKRole.SOURCE == "source"
        assert VTKRole.UNKNOWN == "unknown"


class TestVTKMethod:
    def test_minimal_construction(self):
        m = VTKMethod(name="GetOutput")
        assert m.name == "GetOutput"
        assert m.signatures == []
        assert m.doc == ""
        assert m.is_static is False
        assert m.is_property is False

    def test_full_construction(self):
        m = VTKMethod(
            name="SetInput",
            signatures=["SetInput(data: vtkDataObject) -> None"],
            doc="Set the input data.",
            is_static=True,
            is_property=False,
        )
        assert m.signatures == ["SetInput(data: vtkDataObject) -> None"]
        assert m.is_static is True


class TestVTKDocRecord:
    def test_minimal_construction(self):
        r = VTKDocRecord(class_name="vtkActor", module_name="vtkRenderingCore")
        assert r.class_name == "vtkActor"
        assert r.module_name == "vtkRenderingCore"
        assert r.schema_version == SCHEMA_VERSION
        assert r.role == VTKRole.UNKNOWN
        assert r.methods == []
        assert r.inheritance == []

    def test_content_hash_auto_computed(self):
        r = VTKDocRecord(class_name="vtkActor", module_name="vtkRenderingCore")
        expected = sha1(b"vtkActor").hexdigest()
        assert r.content_hash == expected

    def test_explicit_content_hash_preserved(self):
        r = VTKDocRecord(
            class_name="vtkActor",
            module_name="vtkRenderingCore",
            content_hash="abc123",
        )
        assert r.content_hash == "abc123"

    def test_unknown_role_mapped(self):
        r = VTKDocRecord(
            class_name="vtkFoo",
            module_name="vtkSomething",
            role="bogus_role_not_in_enum",
        )
        assert r.role == VTKRole.UNKNOWN

    def test_known_role_preserved(self):
        r = VTKDocRecord(
            class_name="vtkFoo",
            module_name="vtkSomething",
            role="filter",
        )
        assert r.role == VTKRole.FILTER

    def test_methods_populated_from_structured_docs(self):
        structured_docs = {
            "sections": {
                "Methods defined here": {
                    "methods": {
                        "GetOutput": "GetOutput() -> vtkDataObject\n\nReturn the output data.",
                    }
                }
            }
        }
        r = VTKDocRecord(
            class_name="vtkFoo",
            module_name="vtkSomething",
            structured_docs=structured_docs,
        )
        assert len(r.methods) == 1
        assert r.methods[0].name == "GetOutput"
        assert r.methods[0].doc == "Return the output data."

    def test_explicit_methods_not_overridden_by_structured_docs(self):
        structured_docs = {
            "sections": {
                "Methods defined here": {
                    "methods": {
                        "GetOutput": "GetOutput() -> vtkDataObject\n\nReturn the output.",
                    }
                }
            }
        }
        explicit_methods = [VTKMethod(name="MyMethod")]
        r = VTKDocRecord(
            class_name="vtkFoo",
            module_name="vtkSomething",
            methods=explicit_methods,
            structured_docs=structured_docs,
        )
        assert len(r.methods) == 1
        assert r.methods[0].name == "MyMethod"

    def test_roundtrip_json(self):
        r = VTKDocRecord(
            class_name="vtkActor",
            module_name="vtkRenderingCore",
            vtk_version="9.3.0",
            role="renderer",
            methods=[VTKMethod(name="GetBounds", doc="Return bounds.")],
            synopsis="Represents an actor in a rendered scene.",
        )
        serialised = r.model_dump_json()
        restored = VTKDocRecord.model_validate_json(serialised)
        assert restored.class_name == r.class_name
        assert restored.vtk_version == r.vtk_version
        assert restored.role == VTKRole.RENDERER
        assert restored.methods[0].name == "GetBounds"
        assert restored.synopsis == r.synopsis

    def test_optional_fields_default_to_none(self):
        r = VTKDocRecord(class_name="vtkFoo", module_name="m")
        assert r.synopsis is None
        assert r.action_phrase is None
        assert r.visibility_score is None
        assert r.input_datatype is None
        assert r.output_datatype is None
