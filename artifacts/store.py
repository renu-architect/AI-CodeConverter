"""Versioned artifact storage with content hashing."""

import hashlib
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from artifacts.models import ArtifactRef
from utils.exceptions import ArtifactNotFoundError
from utils.logging import get_logger

logger = get_logger("artifacts.store")

ARTIFACT_EXTENSIONS = {
    "project.json": ".json",
    "Understanding.md": ".md",
    "MigrationPlan.md": ".md",
    "converted_code": ".py",
    "ConversionNotes.md": ".md",
    "MigrationSummary.md": ".md",
    "Review.md": ".md",
    "Validation.md": ".md",
    "TestCases.md": ".md",
    "README.md": ".md",
    "Metrics.json": ".json",
    "approval_record.json": ".json",
    "migration_state.json": ".json",
}


class ArtifactStore(ABC):
    """Abstract base class for artifact storage."""

    @abstractmethod
    def write(
        self, project_id: str, job_id: str, artifact_type: str, content: str
    ) -> ArtifactRef: ...

    @abstractmethod
    def read_latest(self, project_id: str, job_id: str, artifact_type: str) -> str: ...

    @abstractmethod
    def read_version(
        self, project_id: str, job_id: str, artifact_type: str, version: int
    ) -> str: ...

    @abstractmethod
    def list_versions(
        self, project_id: str, job_id: str, artifact_type: str
    ) -> list[ArtifactRef]: ...


class FileArtifactStore(ArtifactStore):
    """Filesystem-based versioned artifact store."""

    def __init__(self, base_dir: str | Path = "artifacts") -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _artifact_dir(self, project_id: str, job_id: str, artifact_type: str) -> Path:
        return self.base_dir / project_id / job_id / artifact_type

    def _get_extension(self, artifact_type: str) -> str:
        return ARTIFACT_EXTENSIONS.get(artifact_type, ".md")

    def _next_version(self, artifact_dir: Path) -> int:
        if not artifact_dir.exists():
            return 1
        versions = []
        for f in artifact_dir.iterdir():
            if f.stem.startswith("v") and f.stem[1:].isdigit():
                versions.append(int(f.stem[1:]))
        return max(versions, default=0) + 1

    @staticmethod
    def _content_hash(content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def write(
        self, project_id: str, job_id: str, artifact_type: str, content: str
    ) -> ArtifactRef:
        artifact_dir = self._artifact_dir(project_id, job_id, artifact_type)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        version = self._next_version(artifact_dir)
        ext = self._get_extension(artifact_type)
        file_path = artifact_dir / f"v{version}{ext}"
        file_path.write_text(content, encoding="utf-8")

        content_hash = self._content_hash(content)
        ref = ArtifactRef(
            project_id=project_id,
            job_id=job_id,
            artifact_type=artifact_type,
            version=version,
            path=str(file_path),
            content_hash=content_hash,
            created_at=datetime.now(timezone.utc),
        )

        logger.info(
            "Artifact written",
            extra={
                "project_id": project_id,
                "job_id": job_id,
                "artifact_type": artifact_type,
                "version": version,
            },
        )
        return ref

    def read_latest(self, project_id: str, job_id: str, artifact_type: str) -> str:
        versions = self.list_versions(project_id, job_id, artifact_type)
        if not versions:
            raise ArtifactNotFoundError(
                f"No artifacts found: {project_id}/{job_id}/{artifact_type}"
            )
        latest = max(versions, key=lambda v: v.version)
        return Path(latest.path).read_text(encoding="utf-8")

    def read_version(
        self, project_id: str, job_id: str, artifact_type: str, version: int
    ) -> str:
        ext = self._get_extension(artifact_type)
        file_path = self._artifact_dir(project_id, job_id, artifact_type) / f"v{version}{ext}"
        if not file_path.exists():
            raise ArtifactNotFoundError(
                f"Artifact not found: {project_id}/{job_id}/{artifact_type}/v{version}"
            )
        return file_path.read_text(encoding="utf-8")

    def list_versions(
        self, project_id: str, job_id: str, artifact_type: str
    ) -> list[ArtifactRef]:
        artifact_dir = self._artifact_dir(project_id, job_id, artifact_type)
        if not artifact_dir.exists():
            return []

        refs: list[ArtifactRef] = []
        for file_path in sorted(artifact_dir.iterdir()):
            if file_path.stem.startswith("v") and file_path.stem[1:].isdigit():
                version = int(file_path.stem[1:])
                content = file_path.read_text(encoding="utf-8")
                refs.append(
                    ArtifactRef(
                        project_id=project_id,
                        job_id=job_id,
                        artifact_type=artifact_type,
                        version=version,
                        path=str(file_path),
                        content_hash=self._content_hash(content),
                        created_at=datetime.fromtimestamp(
                            file_path.stat().st_mtime, tz=timezone.utc
                        ),
                    )
                )
        return refs

    def write_json(
        self, project_id: str, job_id: str, artifact_type: str, data: dict
    ) -> ArtifactRef:
        return self.write(project_id, job_id, artifact_type, json.dumps(data, indent=2))

    def read_latest_json(
        self, project_id: str, job_id: str, artifact_type: str
    ) -> dict:
        content = self.read_latest(project_id, job_id, artifact_type)
        return json.loads(content)

    def has_artifact(self, project_id: str, job_id: str, artifact_type: str) -> bool:
        """Return True if at least one version of the artifact exists."""
        return bool(self.list_versions(project_id, job_id, artifact_type))
