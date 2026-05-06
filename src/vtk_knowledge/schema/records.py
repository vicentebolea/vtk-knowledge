from enum import Enum
from hashlib import sha1
from typing import Optional
from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0.0"


class VTKRole(str, Enum):
    SOURCE = "source"
    INPUT = "input"
    FILTER = "filter"
    MAPPER = "mapper"
    RENDERER = "renderer"
    SCENE = "scene"
    PROPERTIES = "properties"
    INFRASTRUCTURE = "infrastructure"
    OUTPUT = "output"
    UTILITY = "utility"
    COLOR = "color"
    UNKNOWN = "unknown"


class VTKMethod(BaseModel):
    name: str
    signatures: list[str] = []
    doc: str = ""
    is_static: bool = False
    is_property: bool = False


class VTKDocRecord(BaseModel):
    """Single class record — the unit of the knowledge artifact."""

    schema_version: str = Field(default=SCHEMA_VERSION)
    vtk_version: str = ""
    class_name: str
    module_name: str
    class_doc: str = ""
    role: VTKRole = VTKRole.UNKNOWN
    input_datatype: Optional[str] = None
    output_datatype: Optional[str] = None
    methods: list[VTKMethod] = []
    semantic_methods: list[str] = []
    inheritance: list[str] = []
    synopsis: Optional[str] = None
    action_phrase: Optional[str] = None
    visibility_score: Optional[float] = None
    structured_docs: dict = {}
    content_hash: str = ""

    @model_validator(mode="before")
    @classmethod
    def _compat_and_defaults(cls, data: dict) -> dict:
        """Handle backwards compatibility with the pre-Pydantic JSONL format."""
        if isinstance(data, dict):
            # role: accept old string values not in the enum by mapping to UNKNOWN
            role_val = data.get("role", "")
            if isinstance(role_val, str) and role_val and role_val not in {
                r.value for r in VTKRole
            }:
                data["role"] = VTKRole.UNKNOWN.value

            # methods: populate from structured_docs if not supplied
            if not data.get("methods"):
                methods = []
                structured_docs = data.get("structured_docs", {})
                sections = structured_docs.get("sections", {}) if isinstance(structured_docs, dict) else {}
                for section_methods in sections.values():
                    if isinstance(section_methods, dict):
                        for m_name, m_body in section_methods.get("methods", {}).items():
                            sig, _, doc = m_body.partition("\n\n")
                            methods.append({
                                "name": m_name,
                                "signatures": [sig.strip()] if sig.strip() else [],
                                "doc": doc.strip(),
                            })
                data["methods"] = methods

            # content_hash: compute from class_name if missing
            if not data.get("content_hash"):
                data["content_hash"] = sha1(
                    data.get("class_name", "").encode()
                ).hexdigest()

        return data
