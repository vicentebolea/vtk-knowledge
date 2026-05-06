# vtk-knowledge

Pydantic schema, in-memory index, and build pipeline for VTK API knowledge artifacts.

## Installation

```bash
pip install vtk-knowledge          # schema + index (no VTK required at runtime)
pip install vtk-knowledge[build]   # adds extraction pipeline (requires VTK + LiteLLM)
```

## Usage

```python
from vtk_knowledge import VTKAPIIndex

index = VTKAPIIndex.from_jsonl("vtk-knowledge-9.3.0.jsonl")
record = index.get_class("vtkSphereSource")
print(record.synopsis)
```

## Build pipeline

```bash
vtk-knowledge extract -o extracted.jsonl
vtk-knowledge enrich extracted.jsonl -o enriched.jsonl --model openai/gpt-4o-mini
vtk-knowledge build --output-dir .
```

## Architecture

Part of the [VTK LLM tooling](https://github.com/vicentebolea/vtk-llm-architecture) stack:

- **vtk-knowledge** (this repo) — Layer 1: knowledge schema + artifact
- [vtk-index](https://github.com/vicentebolea/vtk-index) — Layer 2: chunking + retrieval
- [vtk-validate](https://github.com/vicentebolea/vtk-validate) — Layer 3: AST validation
- [vtk-mcp](https://github.com/vicentebolea/vtk-mcp) — Layer 4: MCP gateway
