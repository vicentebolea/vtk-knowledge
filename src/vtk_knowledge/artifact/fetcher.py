"""Download a published vtk-knowledge JSONL artifact by VTK version."""

import io
import json
import logging
import tarfile
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_DIR = Path.home() / ".cache" / "vtk-knowledge"

_GITHUB_BASE = (
    "https://github.com/patrickoleary/vtk-knowledge/releases/download/{vtk_version}/vtk-knowledge-{vtk_version}.jsonl"
)

_GHCR_BASE = "https://ghcr.io"
_DEFAULT_REPOSITORY = "vicentebolea/vtk-knowledge"


def _ghcr_token(repository: str) -> str:
    """Obtain an anonymous pull token for a public ghcr.io repository."""
    url = f"{_GHCR_BASE}/token?scope=repository:{repository}:pull&service=ghcr.io"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read())["token"]


def fetch_from_ghcr(
    vtk_version: str,
    repository: str = _DEFAULT_REPOSITORY,
    cache_dir: Path = _CACHE_DIR,
) -> Path:
    """Download the knowledge JSONL by pulling it from a ghcr.io OCI image.

    The image at ``ghcr.io/{repository}:{vtk_version}`` is a FROM-scratch image
    whose single layer is a tar containing ``/vtk-knowledge.jsonl``.  This
    function pulls the manifest, downloads the layer blob, and extracts the
    JSONL without requiring docker or podman.

    Args:
        vtk_version: VTK version tag, e.g. ``"9.6.1"``.
        repository: ghcr.io repository path (owner/name), lower-cased.
        cache_dir: Local cache directory.

    Returns:
        Absolute ``Path`` to the local JSONL file.

    Raises:
        RuntimeError: If any network or extraction step fails.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    local_path = cache_dir / f"vtk-knowledge-{vtk_version}.jsonl"
    if local_path.exists():
        return local_path

    repo = repository.lower()
    try:
        token = _ghcr_token(repo)
        headers = {"Authorization": f"Bearer {token}"}

        # Fetch manifest to find the layer digest
        manifest_url = f"{_GHCR_BASE}/v2/{repo}/manifests/{vtk_version}"
        req = urllib.request.Request(
            manifest_url,
            headers={
                **headers,
                "Accept": (
                    "application/vnd.oci.image.manifest.v1+json,application/vnd.docker.distribution.manifest.v2+json"
                ),
            },
        )
        with urllib.request.urlopen(req) as resp:
            manifest = json.loads(resp.read())

        digest = manifest["layers"][0]["digest"]
        logger.info("Pulling layer %s from ghcr.io/%s:%s", digest[:19], repo, vtk_version)

        # Download the blob (a gzipped tar of the image layer)
        blob_url = f"{_GHCR_BASE}/v2/{repo}/blobs/{digest}"
        req = urllib.request.Request(blob_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            blob = resp.read()

        # Extract the JSONL from the layer tar
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:*") as tar:
            member = next(m for m in tar.getmembers() if m.name.endswith(".jsonl"))
            extracted = tar.extractfile(member)
            if extracted is None:
                raise RuntimeError("JSONL member is not a regular file in the layer tar")
            local_path.write_bytes(extracted.read())

    except Exception as exc:
        raise RuntimeError(f"Failed to pull vtk-knowledge artifact from ghcr.io/{repo}:{vtk_version}: {exc}") from exc

    logger.info("Saved artifact to %s", local_path)
    return local_path


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
        raise RuntimeError(f"Failed to download vtk-knowledge artifact for {vtk_version}: {exc}") from exc
    return local_path
