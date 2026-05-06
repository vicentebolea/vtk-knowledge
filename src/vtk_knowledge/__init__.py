"""vtk-knowledge — schema, index, and build pipeline for VTK API knowledge artifacts."""

__version__ = "1.0.0"

from .index.api_index import VTKAPIIndex
from .schema.records import SCHEMA_VERSION, VTKDocRecord, VTKMethod, VTKRole

__all__ = [
    "VTKAPIIndex",
    "SCHEMA_VERSION",
    "VTKDocRecord",
    "VTKMethod",
    "VTKRole",
]
