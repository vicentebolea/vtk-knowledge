# vtk-knowledge

VTK API knowledge base for LLM tooling. One JSONL record per class, extracted
from the VTK Python runtime and enriched with LLM-generated metadata. The rest
of the stack (retrieval, validation, MCP server) loads this file at startup and
does not need VTK installed.

This is Layer 1 of a four-layer stack:

```
vtk-knowledge  - schema, artifact, in-memory index          (this repo)
vtk-index      - chunking, dense+sparse embeddings, Qdrant
vtk-validate   - AST-based VTK code validation
vtk-mcp        - MCP gateway, 25 tools over stdio/http
```

Each layer only depends on layers below it. `VTKAPIIndex` lives here and is
the single point of truth for the VTK API across the whole stack.

## Install

With uv (recommended):

```bash
uv add vtk-knowledge                # schema + index, no VTK needed
uv add "vtk-knowledge[build]"       # adds extraction pipeline (needs VTK + LiteLLM)
```

With pip:

```bash
pip install vtk-knowledge
pip install "vtk-knowledge[build]"
```

For development:

```bash
git clone https://github.com/vicentebolea/vtk-knowledge
cd vtk-knowledge
uv sync --extra dev         # installs all dev deps from uv.lock
uv run pytest               # run tests
uv run vtk-knowledge --help # try the CLI
```

## Usage

```python
from vtk_knowledge import VTKAPIIndex

# pull from ghcr.io on first call, served from cache (~/.cache/vtk-knowledge/) after that
idx = VTKAPIIndex.from_artifact("9.6.1")
idx = VTKAPIIndex.from_artifact("9.6.1", cache_dir="/tmp/my-cache")  # custom cache dir

# load a local file directly
idx = VTKAPIIndex.from_jsonl("vtk-knowledge-9.6.1.jsonl")

r = idx.get_class("vtkSphereSource")
print(r.synopsis)         # "Create a polygonal sphere with configurable radius and resolution."
print(r.action_phrase)    # "sphere generation"
print(r.visibility_score) # 0.85
print(r.role.value)       # "source"
print(len(r.methods))     # 253
```

## Get the artifact from the OCI image

After each build the JSONL is pushed as a `FROM scratch` image to ghcr.io.
The image has one file: `/vtk-knowledge.jsonl`.

```bash
# podman
ctr=$(podman create ghcr.io/vicentebolea/vtk-knowledge:9.6.1 noop)
podman cp "$ctr:/vtk-knowledge.jsonl" .
podman rm "$ctr"

# docker
ctr=$(docker create ghcr.io/vicentebolea/vtk-knowledge:9.6.1)
docker cp "$ctr:/vtk-knowledge.jsonl" .
docker rm "$ctr"
```

## Build the artifact yourself

Requires `pip install vtk-knowledge[build]` and VTK installed.

```bash
# extract from the running VTK Python runtime
vtk-knowledge extract -o extracted.jsonl

# enrich with an LLM (any LiteLLM model string works)
ANTHROPIC_API_KEY=sk-ant-... \
vtk-knowledge enrich extracted.jsonl \
  --output enriched.jsonl \
  --model anthropic/claude-haiku-4-5 \
  --max-concurrent 20

# one-shot: extract + enrich + write versioned file
vtk-knowledge build \
  --model anthropic/claude-haiku-4-5 \
  --output-dir ./artifacts/
# writes artifacts/vtk-knowledge-9.6.1.jsonl
```

`enrich` is idempotent: records that already have `synopsis`, `action_phrase`,
and `visibility_score` are skipped. Safe to resume after a partial run.

## CI build workflow

`workflow_dispatch` in `.github/workflows/build-artifact.yml`:

1. **Actions -> Build Knowledge Artifact -> Run workflow**
2. Set the model (e.g. `anthropic/claude-haiku-4-5`)
3. Add `LLM_API_KEY` under **Settings -> Secrets and variables -> Actions**

The workflow runs `vtk-knowledge build`, wraps the output in a scratch OCI image,
and pushes to `ghcr.io/{owner}/vtk-knowledge:{vtk_version}` and `:latest`.

## Code layout

```
src/vtk_knowledge/
  schema/records.py      # VTKDocRecord, VTKMethod, VTKRole (Pydantic)
  index/api_index.py     # VTKAPIIndex - O(1) dict lookups, single-pass load
  pipeline/extract.py    # VTK introspection (needs vtk installed)
  pipeline/enrich.py     # async LiteLLM enrichment, idempotent
  pipeline/cli.py        # Typer CLI: extract / enrich / build
  artifact/fetcher.py    # download versioned artifacts from GitHub Releases
```

## Related repos

| Repo | Layer | What it does |
|---|---|---|
| **vtk-knowledge** (here) | 1 | Schema, artifact, index |
| [vtk-index](https://github.com/vicentebolea/vtk-index) | 2 | Chunking, embeddings, Qdrant |
| [vtk-validate](https://github.com/vicentebolea/vtk-validate) | 3 | AST validation of VTK code |
| [vtk-mcp](https://github.com/Kitware/vtk-mcp) | 4 | MCP gateway for LLM assistants |

---

## Artifact schema

One `VTKDocRecord` per class:

| Field | Where it comes from | What it is |
|---|---|---|
| `class_name`, `module_name` | extraction | class name + `vtkmodules` import path |
| `class_doc` | extraction | docstring text from `help()` |
| `methods` | extraction | list of methods with name, signature, doc |
| `inheritance` | extraction | full MRO chain |
| `role` | extraction | `source`, `filter`, `mapper`, `renderer`, `scene`, etc. |
| `input_datatype`, `output_datatype` | extraction | pipeline port types |
| `semantic_methods` | extraction | methods defined on this class (not inherited) |
| `synopsis` | LLM | one sentence, max 20 words |
| `action_phrase` | LLM | noun phrase, max 5 words |
| `visibility_score` | LLM | 0-1, how often users reference this class directly |
| `vtk_version`, `schema_version`, `content_hash` | metadata | versioning and integrity |

## Sample records

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
  "semantic_methods": ["GenerateNormalsOff", "GenerateNormalsOn", "GetCenter", "..."],
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
