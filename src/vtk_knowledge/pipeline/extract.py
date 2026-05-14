"""Extract VTK class records via Python runtime introspection.

Requires VTK to be installed. Produces records with all fields populated
*except* the LLM-enriched ones (synopsis, action_phrase, visibility_score).
"""

from __future__ import annotations

import importlib
import io
import json
import logging
import pkgutil
import re
from hashlib import sha1
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _get_vtk_version() -> str:
    """Return the installed VTK version string."""
    try:
        import vtkmodules

        return getattr(vtkmodules, "__version__", "") or ""
    except ImportError:
        return ""


def _get_vtk_classes() -> dict[str, list[tuple[str, str]]]:
    """Discover VTK classes grouped by module.

    Returns:
        Dict mapping module names to lists of (full_module_path, class_name).
    """
    import vtkmodules

    module_classes: dict[str, list[tuple[str, str]]] = {}
    for _importer, modname, _ispkg in pkgutil.iter_modules(vtkmodules.__path__):
        if not modname.startswith("vtk"):
            continue
        full_module = f"vtkmodules.{modname}"
        try:
            module = importlib.import_module(full_module)
        except Exception:
            continue
        for name in dir(module):
            if name.startswith("vtk") and not name.startswith("vtk_"):
                obj = getattr(module, name, None)
                if isinstance(obj, type):
                    module_classes.setdefault(modname, []).append((full_module, name))
    return module_classes


def _parse_help(class_name: str) -> dict[str, Any]:
    """Run help() on *class_name* and parse the output into structured fields."""
    try:
        import vtk

        vtk_class = getattr(vtk, class_name, None)
        if vtk_class is None:
            return {}
        buf = io.StringIO()
        import contextlib

        with contextlib.redirect_stdout(buf):
            help(vtk_class)
        return _parse_help_text(buf.getvalue())
    except Exception as exc:
        logger.debug("help() failed for %s: %s", class_name, exc)
        return {}


def _parse_help_text(text: str) -> dict[str, Any]:
    """Convert raw help() output into structured_docs and class_doc."""
    class_doc = ""
    sections: dict[str, Any] = {}
    current_section: str | None = None
    current_method: str | None = None
    method_lines: list[str] = []

    for line in text.splitlines():
        # Section header
        m = re.match(r"^ \|  ([-\w ]+ defined here):$", line)
        if m:
            if current_method and current_section:
                sections[current_section]["methods"][current_method] = "\n".join(method_lines).strip()
            current_section = m.group(1)
            sections[current_section] = {"methods": {}}
            current_method = None
            method_lines = []
            continue

        if current_section is None:
            # Before first section — docstring content is inside " |  " lines
            if line.startswith(" |  "):
                stripped = line[4:].strip()
                if stripped:
                    class_doc += stripped + "\n"
            continue

        # Method header inside a section
        if re.match(r"^ \|  \w+", line) and not line.startswith(" |   "):
            if current_method:
                sections[current_section]["methods"][current_method] = "\n".join(method_lines).strip()
            current_method = line.strip().split("(")[0].lstrip("| ").strip()
            method_lines = [line.strip().lstrip("| ")]
            continue

        if current_method:
            method_lines.append(line.strip().lstrip("| "))

    # flush last method
    if current_method and current_section:
        sections[current_section]["methods"][current_method] = "\n".join(method_lines).strip()

    return {"class_doc": class_doc.strip(), "structured_docs": {"sections": sections}}


def _get_inheritance(cls: type) -> list[str]:
    """Return MRO ancestor names for *cls*, excluding 'object'."""
    import inspect

    return [c.__name__ for c in inspect.getmro(cls)[1:] if c.__name__ != "object"]


# Ancestor sets used for MRO-based role classification (no instantiation needed)
_MAPPER_ANCESTORS = frozenset(
    {
        "vtkMapper",
        "vtkAbstractMapper",
        "vtkAbstractMapper3D",
        "vtkVolumeMapper",
        "vtkImageMapper",
        "vtkImageMapper3D",
        "vtkMapper2D",
        "vtkPolyDataMapper",
        "vtkPolyDataMapper2D",
        "vtkUnstructuredGridVolumeMapper",
    }
)
_RENDERER_ANCESTORS = frozenset({"vtkRenderer", "vtkVolumeRenderer"})
_SCENE_ANCESTORS = frozenset(
    {
        "vtkProp",
        "vtkProp3D",
        "vtkActor",
        "vtkVolume",
        "vtkActor2D",
        "vtkRenderWindow",
        "vtkRenderWindowInteractor",
        "vtkCamera",
        "vtkLight",
        "vtkAssembly",
        "vtkFollower",
    }
)
_PROPERTY_ANCESTORS = frozenset(
    {
        "vtkProperty",
        "vtkProperty2D",
        "vtkTextProperty",
        "vtkVolumeProperty",
    }
)
_COLOR_ANCESTORS = frozenset(
    {
        "vtkScalarsToColors",
        "vtkLookupTable",
        "vtkColorTransferFunction",
        "vtkDiscretizableColorTransferFunction",
        "vtkPiecewiseFunction",
    }
)
# Never instantiate these — they open display connections or have side effects
_NO_INSTANTIATE = frozenset(
    {
        "vtkRenderWindow",
        "vtkRenderWindowInteractor",
        "vtkRenderer",
        "vtkOpenGLRenderWindow",
    }
)


def _classify_role(class_name: str, cls: type, inheritance: list[str]) -> str:
    """Determine role using MRO checks first, then port-count for algorithms."""
    # Include the class itself so base classes (e.g. vtkProperty) match their own set
    ancestor_set = set(inheritance) | {class_name}

    if ancestor_set & _MAPPER_ANCESTORS:
        return "mapper"
    if ancestor_set & _RENDERER_ANCESTORS:
        return "renderer"
    if ancestor_set & _PROPERTY_ANCESTORS:
        return "properties"
    if ancestor_set & _COLOR_ANCESTORS:
        return "color"
    if ancestor_set & _SCENE_ANCESTORS:
        return "scene"

    if "vtkAlgorithm" in ancestor_set and class_name not in _NO_INSTANTIATE:
        try:
            obj = cls()
            n_in = obj.GetNumberOfInputPorts()
            n_out = obj.GetNumberOfOutputPorts()
            del obj
            if n_in == 0 and n_out > 0:
                return "source"
            if n_in > 0 and n_out > 0:
                return "filter"
            if n_in > 0 and n_out == 0:
                return "output"
        except Exception:
            pass
        name_lower = class_name.lower()
        if any(name_lower.endswith(s) for s in ("reader", "source", "generator", "importer")):
            return "source"
        if any(name_lower.endswith(s) for s in ("writer", "exporter")):
            return "output"
        return "filter"

    name_lower = class_name.lower()
    if any(s in name_lower for s in ("manager", "factory", "registry")):
        return "infrastructure"
    return "unknown"


# Ordered pairs of (ancestor, output_type); first match wins.
_OUTPUT_BY_ANCESTOR: tuple[tuple[str, str], ...] = (
    ("vtkPolyDataAlgorithm", "vtkPolyData"),
    ("vtkImageAlgorithm", "vtkImageData"),
    ("vtkUnstructuredGridAlgorithm", "vtkUnstructuredGrid"),
    ("vtkStructuredGridAlgorithm", "vtkStructuredGrid"),
    ("vtkRectilinearGridAlgorithm", "vtkRectilinearGrid"),
    ("vtkTableAlgorithm", "vtkTable"),
    ("vtkGraphAlgorithm", "vtkGraph"),
    ("vtkTreeAlgorithm", "vtkTree"),
    ("vtkMultiBlockDataSetAlgorithm", "vtkMultiBlockDataSet"),
    ("vtkCompositeDataSetAlgorithm", "vtkCompositeDataSet"),
    ("vtkDataSetAlgorithm", "vtkDataSet"),
)


def _get_datatypes(inheritance: list[str]) -> tuple[str | None, str | None]:
    """Infer output_datatype from the algorithm's base class (no instantiation)."""
    ancestor_set = set(inheritance)
    for ancestor, output_type in _OUTPUT_BY_ANCESTOR:
        if ancestor in ancestor_set:
            return None, output_type
    return None, None


def _semantic_methods_from_parsed(parsed: dict[str, Any]) -> list[str]:
    """Return method names defined directly on the class (not inherited)."""
    sections = parsed.get("structured_docs", {}).get("sections", {})
    own = sections.get("Methods defined here", {}).get("methods", {})
    return sorted(own.keys())


def extract_records(vtk_version: str = "") -> list[dict[str, Any]]:
    """Extract raw records (without LLM enrichment) for all VTK classes.

    Args:
        vtk_version: VTK version to tag records with. Auto-detected if empty.

    Returns:
        List of record dicts ready for JSON serialisation.
    """
    if not vtk_version:
        vtk_version = _get_vtk_version()

    module_classes = _get_vtk_classes()
    records: list[dict[str, Any]] = []

    for modname, class_tuples in module_classes.items():
        for full_module, class_name in class_tuples:
            parsed = _parse_help(class_name)

            cls: type | None = None
            inheritance: list[str] = []
            try:
                mod = importlib.import_module(full_module)
                cls = getattr(mod, class_name, None)
                if cls is not None:
                    inheritance = _get_inheritance(cls)
            except Exception:
                pass

            role = "unknown"
            input_dt: str | None = None
            output_dt: str | None = None
            if cls is not None:
                role = _classify_role(class_name, cls, inheritance)
                input_dt, output_dt = _get_datatypes(inheritance)

            record: dict[str, Any] = {
                "schema_version": "1.0.0",
                "vtk_version": vtk_version,
                "class_name": class_name,
                "module_name": full_module,
                "class_doc": parsed.get("class_doc", ""),
                "role": role,
                "input_datatype": input_dt,
                "output_datatype": output_dt,
                "semantic_methods": _semantic_methods_from_parsed(parsed),
                "structured_docs": parsed.get("structured_docs", {}),
                "inheritance": inheritance,
                "methods": [],
                "content_hash": sha1(class_name.encode()).hexdigest(),
            }
            records.append(record)

    return records


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    """Serialise records to JSONL."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Wrote %d records to %s", len(records), output_path)
