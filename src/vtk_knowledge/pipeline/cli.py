"""CLI for the vtk-knowledge build pipeline.

Commands:
    vtk-knowledge download   -- pull a published artifact from ghcr.io
    vtk-knowledge extract    -- VTK runtime → extracted.jsonl
    vtk-knowledge enrich     -- extracted.jsonl + LLM → enriched.jsonl
    vtk-knowledge build      -- convenience wrapper: extract → enrich → final artifact
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

app = typer.Typer(
    name="vtk-knowledge",
    help="VTK knowledge artifact build pipeline.",
    no_args_is_help=True,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


@app.command()
def download(
    vtk_version: str = typer.Argument(..., help="VTK version to download, e.g. 9.6.1"),
    output_dir: Path = typer.Option(
        Path("."),
        "--output-dir",
        "-o",
        help="Directory to write the JSONL file into.",
    ),
    repository: str = typer.Option(
        "vicentebolea/vtk-knowledge",
        "--repository",
        "-r",
        help="ghcr.io owner/name to pull from.",
    ),
) -> None:
    """Download a published artifact from ghcr.io (no VTK or LLM required)."""
    import shutil

    from ..artifact.fetcher import _CACHE_DIR, fetch_from_ghcr

    try:
        cached = fetch_from_ghcr(vtk_version, repository=repository)
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    dest = output_dir / cached.name
    if dest.resolve() != cached.resolve():
        output_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(cached, dest)

    typer.echo(f"Artifact written to {dest}  (cached at {_CACHE_DIR / cached.name})")


@app.command()
def extract(
    output: Path = typer.Option(
        Path("extracted.jsonl"),
        "--output",
        "-o",
        help="Output JSONL path for extracted records.",
    ),
    vtk_version: str = typer.Option("", "--vtk-version", help="Override VTK version tag on records."),
) -> None:
    """Extract VTK class records via Python runtime introspection."""
    from .extract import extract_records, write_jsonl

    try:
        records = extract_records(vtk_version=vtk_version)
    except ModuleNotFoundError as exc:
        typer.echo(f"Error: VTK is not installed ({exc}). Install with: pip install vtk", err=True)
        raise typer.Exit(1)
    write_jsonl(records, output)
    typer.echo(f"Extracted {len(records)} records to {output}")


@app.command()
def enrich(
    input_path: Path = typer.Argument(Path("extracted.jsonl"), help="Input extracted JSONL."),
    output: Path = typer.Option(Path("enriched.jsonl"), "--output", "-o", help="Output enriched JSONL."),
    model: str = typer.Option("", "--model", "-m", help="LiteLLM model identifier."),
    max_concurrent: int = typer.Option(10, "--max-concurrent", help="Max parallel LLM requests."),
) -> None:
    """Enrich extracted records with LLM-generated synopsis and metadata."""
    from .enrich import enrich_jsonl

    try:
        enrich_jsonl(input_path, output, model=model, max_concurrent=max_concurrent)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Enriched records written to {output}")


@app.command()
def build(
    output_dir: Path = typer.Option(Path("."), "--output-dir", "-o", help="Directory for final artifact."),
    vtk_version: str = typer.Option("", "--vtk-version", help="Override VTK version tag."),
    model: str = typer.Option("", "--model", "-m", help="LiteLLM model identifier."),
    max_concurrent: int = typer.Option(10, "--max-concurrent"),
) -> None:
    """Run extract → enrich → write versioned artifact."""
    import tempfile

    from .enrich import enrich_jsonl
    from .extract import extract_records, write_jsonl

    with tempfile.TemporaryDirectory() as tmp:
        extracted = Path(tmp) / "extracted.jsonl"
        enriched = Path(tmp) / "enriched.jsonl"

        try:
            records = extract_records(vtk_version=vtk_version)
        except ModuleNotFoundError as exc:
            typer.echo(f"Error: VTK is not installed ({exc}). Install with: pip install vtk", err=True)
            raise typer.Exit(1)
        write_jsonl(records, extracted)

        if model or __import__("os").getenv("LLM_MODEL"):
            enrich_jsonl(extracted, enriched, model=model, max_concurrent=max_concurrent)
            source = enriched
        else:
            typer.echo(
                "Warning: LLM_MODEL not set — skipping enrichment step.",
                err=True,
            )
            source = extracted

        effective_version = vtk_version or records[0].get("vtk_version", "unknown") if records else "unknown"
        artifact_name = f"vtk-knowledge-{effective_version}.jsonl"
        artifact_path = output_dir / artifact_name
        output_dir.mkdir(parents=True, exist_ok=True)
        import shutil

        shutil.copy(source, artifact_path)

    typer.echo(f"Artifact written to {artifact_path}")


if __name__ == "__main__":
    app()
