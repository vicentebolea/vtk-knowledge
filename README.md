# vtk-knowledge

**Layer 1 of the VTK LLM tooling stack.**

`vtk-knowledge` is the knowledge foundation for LLM-assisted VTK development.
It ships a versioned JSONL artifact — one record per VTK class — containing
structured API documentation enriched with LLM-generated fields (`synopsis`,
`action_phrase`, `visibility_score`).  Downstream layers (retrieval, validation,
MCP gateway) all read from this single artifact at startup; no VTK runtime is
needed at query time.

## Architecture

```
vtk-knowledge  (this repo) — Layer 1: schema, artifact, in-memory index
vtk-index                  — Layer 2: chunking, dense+sparse embeddings, Qdrant
vtk-validate               — Layer 3: AST-based VTK code validation
vtk-mcp                    — Layer 4: MCP gateway (25 tools over stdio/http)
```

Dependency direction is strictly top-down: each layer imports only from layers
below it.  `VTKAPIIndex` lives here and is the single source of truth for the
VTK API surface across the whole stack.

## What is in the artifact

Each record (`VTKDocRecord`) covers one VTK class and contains:

| Field | Source | Description |
|---|---|---|
| `class_name`, `module_name` | extraction | Python class + `vtkmodules` path |
| `class_doc` | extraction | docstring from `help()` |
| `methods` | extraction | per-method name, signature, doc |
| `inheritance` | extraction | full MRO ancestor chain |
| `role` | extraction | `source`, `filter`, `mapper`, `renderer`, … |
| `input_datatype`, `output_datatype` | extraction | algorithm port types |
| `semantic_methods` | extraction | methods defined on the class itself |
| `synopsis` | LLM enrichment | one-sentence summary (max 20 words) |
| `action_phrase` | LLM enrichment | noun-phrase primary action (max 5 words) |
| `visibility_score` | LLM enrichment | 0–1 likelihood a user mentions this class |
| `vtk_version`, `schema_version`, `content_hash` | metadata | versioning + integrity |

## Sample records

Three records from the enriched `vtk-knowledge-9.6.1.jsonl` artifact:

```json
{
  "class_name": "vtkSphereSource",
  "module_name": "vtkmodules.vtkFiltersSources",
  "vtk_version": "9.6.1",
  "role": "source",
  "synopsis": "Create a polygonal sphere with configurable radius and resolution.",
  "action_phrase": "sphere generation",
  "visibility_score": 0.85,
  "output_datatype": "vtkPolyData",
  "inheritance": ["vtkPolyDataAlgorithm", "vtkAlgorithm", "vtkObject", "vtkObjectBase"],
  "semantic_methods": ["GenerateNormalsOff", "GenerateNormalsOn", "GetCenter", "GetEndPhi", "..."],
  "methods": [{ "name": "SetRadius", "doc": "Set the radius of the sphere." }, "..."]
}
```

```json
{
  "class_name": "vtkContourFilter",
  "module_name": "vtkmodules.vtkFiltersCore",
  "vtk_version": "9.6.1",
  "role": "filter",
  "synopsis": "Generate isosurfaces and isolines from scalar field data.",
  "action_phrase": "isosurface generation",
  "visibility_score": 0.85,
  "output_datatype": "vtkPolyData",
  "inheritance": ["vtkPolyDataAlgorithm", "vtkAlgorithm", "vtkObject", "vtkObjectBase"],
  "semantic_methods": ["ComputeGradientsOff", "ComputeNormalsOff", "GenerateTrianglesOff", "..."],
  "methods": [{ "name": "SetValue", "doc": "Set a particular contour value at contour number i." }, "..."]
}
```

```json
{
  "class_name": "vtkActor",
  "module_name": "vtkmodules.vtkRenderingCore",
  "vtk_version": "9.6.1",
  "role": "scene",
  "synopsis": "Represents a renderable object with geometry, properties, and transformation in a scene.",
  "action_phrase": "scene object representation",
  "visibility_score": 0.95,
  "output_datatype": null,
  "inheritance": ["vtkProp3D", "vtkProp", "vtkObject", "vtkObjectBase"],
  "semantic_methods": ["ApplyProperties", "ForceOpaqueOff", "ForceOpaqueOn", "..."],
  "methods": [{ "name": "GetBounds", "doc": "Return the bounds of this actor." }, "..."]
}
```

## Installation

```bash
pip install vtk-knowledge          # schema + index only (no VTK required)
pip install vtk-knowledge[build]   # adds the build pipeline (requires VTK + LiteLLM)
```

## Quickstart

### Load from the published artifact

```python
from vtk_knowledge import VTKAPIIndex

# Download from GitHub Container Registry (cached in ~/.cache/vtk-knowledge/)
idx = VTKAPIIndex.from_artifact("9.6.1")

# Or load a local file
idx = VTKAPIIndex.from_jsonl("vtk-knowledge-9.6.1.jsonl")

record = idx.get_class("vtkSphereSource")
print(record.synopsis)        # "Create a polygonal sphere with configurable radius and resolution."
print(record.action_phrase)   # "sphere generation"
print(record.visibility_score)# 0.85
print(record.role.value)      # "source"
print(len(record.methods))    # 253
```

### Pull the artifact from the OCI image

The artifact is published as a scratch OCI image to GitHub Container Registry
after every successful build workflow.  The image contains a single file:
`/vtk-knowledge.jsonl`.

```bash
# Pull and extract with podman
ctr=$(podman create ghcr.io/vicentebolea/vtk-knowledge:9.6.1 noop)
podman cp "$ctr:/vtk-knowledge.jsonl" .
podman rm "$ctr"

# Same with docker
ctr=$(docker create ghcr.io/vicentebolea/vtk-knowledge:9.6.1)
docker cp "$ctr:/vtk-knowledge.jsonl" .
docker rm "$ctr"
```

## Build pipeline

Requires `pip install vtk-knowledge[build]` and a running VTK installation.

```bash
# Step 1 — introspect the installed VTK runtime
vtk-knowledge extract -o extracted.jsonl

# Step 2 — enrich with an LLM (any LiteLLM-compatible model)
ANTHROPIC_API_KEY=sk-ant-... \
vtk-knowledge enrich extracted.jsonl \
  --output enriched.jsonl \
  --model anthropic/claude-haiku-4-5 \
  --max-concurrent 20

# Step 3 — write a versioned artifact
vtk-knowledge build \
  --model anthropic/claude-haiku-4-5 \
  --output-dir ./artifacts/
# → artifacts/vtk-knowledge-9.6.1.jsonl
```

The `enrich` command is **idempotent**: records that already have all three
LLM fields are skipped, so a run can be resumed after interruption.

## Automated build workflow

A `workflow_dispatch` GitHub Actions workflow builds and publishes the artifact
on demand:

1. Go to **Actions → Build Knowledge Artifact → Run workflow**
2. Enter the LiteLLM model identifier (e.g. `anthropic/claude-haiku-4-5`)
3. Set `LLM_API_KEY` as a repository secret in **Settings → Secrets and variables → Actions**

The workflow runs `vtk-knowledge build`, then packages the JSONL into a
`FROM scratch` OCI image and pushes it to
`ghcr.io/{owner}/vtk-knowledge:{vtk_version}` and `:latest`.

## Package structure

```
src/vtk_knowledge/
  schema/records.py      # VTKDocRecord, VTKMethod, VTKRole  (Pydantic)
  index/api_index.py     # VTKAPIIndex  — O(1) dict lookups, loads in one pass
  pipeline/extract.py    # VTK runtime introspection (requires vtk)
  pipeline/enrich.py     # LiteLLM enrichment, async, idempotent
  pipeline/cli.py        # Typer CLI: extract / enrich / build
  artifact/fetcher.py    # Download versioned artifacts from GitHub Releases
```

## Related repositories

| Repo | Layer | Role |
|---|---|---|
| **vtk-knowledge** (this) | 1 | Schema, artifact, index |
| [vtk-index](https://github.com/vicentebolea/vtk-index) | 2 | Chunking, embeddings, Qdrant |
| [vtk-validate](https://github.com/vicentebolea/vtk-validate) | 3 | AST-based VTK code validation |
| [vtk-mcp](https://github.com/Kitware/vtk-mcp) | 4 | MCP gateway for LLM assistants |
