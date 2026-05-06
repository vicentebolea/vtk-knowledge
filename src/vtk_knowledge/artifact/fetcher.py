"""Download a published vtk-knowledge JSONL artifact by VTK version."""

import hashlib
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".cache" / "vtk-knowledge"

_GITHUB_BASE = (
    "https://github.com/patrickoleary/vtk-knowledge/releases/download"
    "/{vtk_version}/vtk-knowledge-{vtk_version}.jsonl"
)


def fetch_knowledge_artifact(vtk_version: str, cache_dir: Path = _CACHE_DIR) -> Path:
    """Return a local path to the knowledge JSONL for *vtk_version*.

    Downloads from GitHub Releases on first call; subsequent calls return the
    cached file.

    Args:
        vtk_version: VTK version string, e.g. ``"9.3.0"``.
        cache_dir: Directory for cached downloads.

    Returns:
        Absolute ``Path`` to the local JSONL file.

    Raises:
        RuntimeError: If the download fails.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_path = cache_dir / f"vtk-knowledge-{vtk_version}.jsonl"
    if local_path.exists():
        return local_path

    url = _GITHUB_BASE.format(vtk_version=vtk_version)
    logger.info("Downloading vtk-knowledge artifact from %s", url)
    try:
        urllib.request.urlretrieve(url, local_path)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download vtk-knowledge artifact for {vtk_version}: {exc}"
        ) from exc
    return local_path
