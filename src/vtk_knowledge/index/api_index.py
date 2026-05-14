"""In-memory query interface over a vtk-knowledge JSONL artifact."""

import logging
from pathlib import Path
from typing import Optional

from ..schema.records import VTKDocRecord, VTKMethod

logger = logging.getLogger(__name__)


class VTKAPIIndex:
    """In-memory query interface over a vtk-knowledge JSONL artifact."""

    def __init__(self, records: list[VTKDocRecord]) -> None:
        self.vtk_version: str = records[0].vtk_version if records else ""
        self.classes: dict[str, VTKDocRecord] = {r.class_name: r for r in records}
        self.modules: dict[str, list[str]] = {}
        for r in records:
            self.modules.setdefault(r.module_name, []).append(r.class_name)
        logger.info(
            "Loaded %d VTK classes from %d modules",
            len(self.classes),
            len(self.modules),
        )

    @classmethod
    def from_jsonl(cls, path: Path) -> "VTKAPIIndex":
        records: list[VTKDocRecord] = []
        with open(path) as f:
            for line in f:
                if line.strip():
                    records.append(VTKDocRecord.model_validate_json(line))
        return cls(records)

    @classmethod
    def from_artifact(cls, vtk_version: str, cache_dir: Optional[Path] = None) -> "VTKAPIIndex":
        """Load by version, pulling from ghcr.io on first call and serving from cache thereafter.

        Args:
            vtk_version: VTK version tag, e.g. ``"9.6.1"``.
            cache_dir: Local cache directory (default: ``~/.cache/vtk-knowledge/``).
        """
        from ..artifact.fetcher import _CACHE_DIR, fetch_from_ghcr

        return cls.from_jsonl(fetch_from_ghcr(vtk_version, cache_dir=cache_dir or _CACHE_DIR))

    # ------------------------------------------------------------------
    # Core query API
    # ------------------------------------------------------------------

    def get_class(self, name: str) -> Optional[VTKDocRecord]:
        return self.classes.get(name)

    # Alias used by older callers
    def get_class_info(self, class_name: str) -> Optional[VTKDocRecord]:
        return self.classes.get(class_name)

    def has_class(self, name: str) -> bool:
        return name in self.classes

    def is_vtk_class(self, name: str) -> bool:
        return name in self.classes

    def get_method(self, class_name: str, method_name: str) -> Optional[VTKMethod]:
        record = self.classes.get(class_name)
        if record is None:
            return None
        for m in record.methods:
            if m.name == method_name:
                return m
        return None

    # Alias used by older callers
    def get_method_info(self, class_name: str, method_name: str) -> Optional[VTKMethod]:
        return self.get_method(class_name, method_name)

    def search_classes(self, query: str, limit: int = 10) -> list[VTKDocRecord]:
        query_lower = query.lower()
        results = [r for name, r in self.classes.items() if query_lower in name.lower()]
        return results[:limit]

    def is_module(self, module_name: str) -> bool:
        return module_name in self.modules

    def classes_in_module(self, module_name: str) -> list[str]:
        return self.modules.get(module_name, [])

    # Alias used by older callers
    def get_module_classes(self, module: str) -> list[str]:
        return self.modules.get(module, [])

    # ------------------------------------------------------------------
    # Convenience accessors (return plain values, not Pydantic models)
    # ------------------------------------------------------------------

    def get_class_module(self, class_name: str) -> Optional[str]:
        r = self.classes.get(class_name)
        return r.module_name if r else None

    def get_class_doc(self, class_name: str) -> Optional[str]:
        r = self.classes.get(class_name)
        return r.class_doc if r else None

    def get_class_synopsis(self, class_name: str) -> Optional[str]:
        r = self.classes.get(class_name)
        return r.synopsis if r else None

    def get_class_action_phrase(self, class_name: str) -> Optional[str]:
        r = self.classes.get(class_name)
        return r.action_phrase if r else None

    def get_class_role(self, class_name: str) -> Optional[str]:
        r = self.classes.get(class_name)
        return r.role.value if r else None

    def get_class_visibility(self, class_name: str) -> Optional[float]:
        r = self.classes.get(class_name)
        return r.visibility_score if r else None

    def get_class_input_datatype(self, class_name: str) -> Optional[str]:
        r = self.classes.get(class_name)
        return r.input_datatype if r else None

    def get_class_output_datatype(self, class_name: str) -> Optional[str]:
        r = self.classes.get(class_name)
        return r.output_datatype if r else None

    def get_class_semantic_methods(self, class_name: str) -> list[str]:
        r = self.classes.get(class_name)
        return r.semantic_methods if r else []

    def get_class_methods(self, class_name: str) -> list[VTKMethod]:
        r = self.classes.get(class_name)
        return r.methods if r else []

    def get_method_doc(self, class_name: str, method_name: str) -> Optional[str]:
        m = self.get_method(class_name, method_name)
        return m.doc if m else None

    def get_method_signature(self, class_name: str, method_name: str) -> Optional[str]:
        m = self.get_method(class_name, method_name)
        if m and m.signatures:
            return m.signatures[0]
        return None
