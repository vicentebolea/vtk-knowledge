"""Tests for vtk_knowledge.index.api_index."""

import pytest

from vtk_knowledge.index.api_index import VTKAPIIndex
from vtk_knowledge.schema.records import VTKDocRecord, VTKMethod


def _make_record(
    class_name: str,
    module_name: str = "vtkTestModule",
    vtk_version: str = "9.3.0",
    **kwargs,
) -> VTKDocRecord:
    return VTKDocRecord(
        class_name=class_name,
        module_name=module_name,
        vtk_version=vtk_version,
        **kwargs,
    )


@pytest.fixture()
def small_index() -> VTKAPIIndex:
    records = [
        _make_record(
            "vtkActor",
            "vtkRenderingCore",
            role="renderer",
            class_doc="Represents an actor.",
            synopsis="Renders geometry in a scene.",
            action_phrase="scene rendering",
            visibility_score=1.0,
            input_datatype="vtkPolyData",
            output_datatype=None,
            methods=[
                VTKMethod(
                    name="GetBounds",
                    signatures=["GetBounds() -> tuple"],
                    doc="Return bounding box.",
                ),
                VTKMethod(name="SetVisibility", doc="Show or hide the actor."),
            ],
        ),
        _make_record(
            "vtkRenderer",
            "vtkRenderingCore",
            role="renderer",
            class_doc="Manages a viewport.",
        ),
        _make_record(
            "vtkPolyDataMapper",
            "vtkRenderingCore",
            role="mapper",
            class_doc="Maps poly data to graphics.",
        ),
        _make_record(
            "vtkSphereSource",
            "vtkFiltersSources",
            role="source",
        ),
    ]
    return VTKAPIIndex(records)


class TestVTKAPIIndexInit:
    def test_vtk_version_from_first_record(self, small_index):
        assert small_index.vtk_version == "9.3.0"

    def test_empty_records_list(self):
        idx = VTKAPIIndex([])
        assert idx.vtk_version == ""
        assert idx.classes == {}
        assert idx.modules == {}

    def test_classes_dict_keyed_by_name(self, small_index):
        assert "vtkActor" in small_index.classes
        assert "vtkRenderer" in small_index.classes

    def test_modules_grouped_correctly(self, small_index):
        assert "vtkRenderingCore" in small_index.modules
        assert "vtkFiltersSources" in small_index.modules
        rendering_classes = set(small_index.modules["vtkRenderingCore"])
        assert "vtkActor" in rendering_classes
        assert "vtkRenderer" in rendering_classes
        assert "vtkPolyDataMapper" in rendering_classes


class TestCoreQueryAPI:
    def test_get_class_existing(self, small_index):
        r = small_index.get_class("vtkActor")
        assert r is not None
        assert r.class_name == "vtkActor"

    def test_get_class_missing(self, small_index):
        assert small_index.get_class("vtkNonExistent") is None

    def test_get_class_info_alias(self, small_index):
        assert small_index.get_class_info("vtkActor") is small_index.get_class("vtkActor")

    def test_has_class_true(self, small_index):
        assert small_index.has_class("vtkActor") is True

    def test_has_class_false(self, small_index):
        assert small_index.has_class("vtkMissing") is False

    def test_is_vtk_class_alias(self, small_index):
        assert small_index.is_vtk_class("vtkActor") is True
        assert small_index.is_vtk_class("vtkMissing") is False

    def test_get_method_found(self, small_index):
        m = small_index.get_method("vtkActor", "GetBounds")
        assert m is not None
        assert m.name == "GetBounds"
        assert m.doc == "Return bounding box."

    def test_get_method_not_found(self, small_index):
        assert small_index.get_method("vtkActor", "NonExistent") is None

    def test_get_method_missing_class(self, small_index):
        assert small_index.get_method("vtkMissing", "GetBounds") is None

    def test_get_method_info_alias(self, small_index):
        assert small_index.get_method_info("vtkActor", "GetBounds") is small_index.get_method("vtkActor", "GetBounds")

    def test_search_classes_match(self, small_index):
        results = small_index.search_classes("Actor")
        names = [r.class_name for r in results]
        assert "vtkActor" in names

    def test_search_classes_case_insensitive(self, small_index):
        results = small_index.search_classes("actor")
        names = [r.class_name for r in results]
        assert "vtkActor" in names

    def test_search_classes_limit(self, small_index):
        results = small_index.search_classes("vtk", limit=2)
        assert len(results) <= 2

    def test_search_classes_no_match(self, small_index):
        assert small_index.search_classes("xyzzy") == []

    def test_is_module_true(self, small_index):
        assert small_index.is_module("vtkRenderingCore") is True

    def test_is_module_false(self, small_index):
        assert small_index.is_module("vtkNoSuchModule") is False

    def test_classes_in_module(self, small_index):
        classes = small_index.classes_in_module("vtkRenderingCore")
        assert "vtkActor" in classes

    def test_classes_in_module_missing(self, small_index):
        assert small_index.classes_in_module("vtkNoSuchModule") == []

    def test_get_module_classes_alias(self, small_index):
        assert small_index.get_module_classes("vtkRenderingCore") == small_index.classes_in_module("vtkRenderingCore")


class TestConvenienceAccessors:
    def test_get_class_module(self, small_index):
        assert small_index.get_class_module("vtkActor") == "vtkRenderingCore"

    def test_get_class_module_missing(self, small_index):
        assert small_index.get_class_module("vtkMissing") is None

    def test_get_class_doc(self, small_index):
        assert small_index.get_class_doc("vtkActor") == "Represents an actor."

    def test_get_class_doc_missing(self, small_index):
        assert small_index.get_class_doc("vtkMissing") is None

    def test_get_class_synopsis(self, small_index):
        assert small_index.get_class_synopsis("vtkActor") == "Renders geometry in a scene."

    def test_get_class_synopsis_none_when_absent(self, small_index):
        assert small_index.get_class_synopsis("vtkRenderer") is None

    def test_get_class_action_phrase(self, small_index):
        assert small_index.get_class_action_phrase("vtkActor") == "scene rendering"

    def test_get_class_role(self, small_index):
        assert small_index.get_class_role("vtkActor") == "renderer"

    def test_get_class_role_missing(self, small_index):
        assert small_index.get_class_role("vtkMissing") is None

    def test_get_class_visibility(self, small_index):
        assert small_index.get_class_visibility("vtkActor") == 1.0

    def test_get_class_visibility_none_when_absent(self, small_index):
        assert small_index.get_class_visibility("vtkRenderer") is None

    def test_get_class_input_datatype(self, small_index):
        assert small_index.get_class_input_datatype("vtkActor") == "vtkPolyData"

    def test_get_class_input_datatype_missing(self, small_index):
        assert small_index.get_class_input_datatype("vtkMissing") is None

    def test_get_class_output_datatype(self, small_index):
        assert small_index.get_class_output_datatype("vtkActor") is None

    def test_get_class_semantic_methods_empty(self, small_index):
        assert small_index.get_class_semantic_methods("vtkActor") == []

    def test_get_class_semantic_methods_missing(self, small_index):
        assert small_index.get_class_semantic_methods("vtkMissing") == []

    def test_get_class_methods(self, small_index):
        methods = small_index.get_class_methods("vtkActor")
        assert len(methods) == 2
        assert methods[0].name == "GetBounds"

    def test_get_class_methods_missing(self, small_index):
        assert small_index.get_class_methods("vtkMissing") == []

    def test_get_method_doc(self, small_index):
        assert small_index.get_method_doc("vtkActor", "GetBounds") == "Return bounding box."

    def test_get_method_doc_missing_method(self, small_index):
        assert small_index.get_method_doc("vtkActor", "NoSuch") is None

    def test_get_method_signature(self, small_index):
        assert small_index.get_method_signature("vtkActor", "GetBounds") == "GetBounds() -> tuple"

    def test_get_method_signature_no_sigs(self, small_index):
        assert small_index.get_method_signature("vtkActor", "SetVisibility") is None

    def test_get_method_signature_missing_class(self, small_index):
        assert small_index.get_method_signature("vtkMissing", "GetBounds") is None


class TestFromJsonl:
    def test_roundtrip(self, small_index, tmp_path):
        jsonl_path = tmp_path / "test.jsonl"
        with open(jsonl_path, "w") as f:
            for r in small_index.classes.values():
                f.write(r.model_dump_json() + "\n")

        idx2 = VTKAPIIndex.from_jsonl(jsonl_path)
        assert set(idx2.classes.keys()) == set(small_index.classes.keys())
        assert idx2.vtk_version == small_index.vtk_version

    def test_blank_lines_skipped(self, tmp_path):
        jsonl_path = tmp_path / "with_blanks.jsonl"
        record = VTKDocRecord(class_name="vtkFoo", module_name="m")
        with open(jsonl_path, "w") as f:
            f.write("\n")
            f.write(record.model_dump_json() + "\n")
            f.write("\n")

        idx = VTKAPIIndex.from_jsonl(jsonl_path)
        assert "vtkFoo" in idx.classes
