"""Atomic artifact files, registered metadata, and descriptor-based scoped reads."""

import hashlib
import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import Field
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from .contracts import AnalysisError, Contract, ErrorCode, Identifier
from .models import AnalysisArtifact, utcnow
from .repository import owned_run, require_postgres
from .publication_validation import ensure_before_deadline


class ArtifactMetadata(Contract):
    id: Identifier
    run_id: Identifier
    mime_type: Annotated[str, Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9!#$&^_.+-]*/[a-zA-Z0-9][a-zA-Z0-9!#$&^_.+-]*$", max_length=200)]
    byte_size: Annotated[int, Field(strict=True, ge=0)]
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    purpose: Annotated[str, Field(min_length=1, max_length=200)]


@dataclass(frozen=True)
class StoredArtifact:
    metadata: ArtifactMetadata
    data: bytes


def artifact_root() -> Path:
    default = Path(__file__).resolve().parents[3] / "analysis-artifacts"
    return Path(os.environ.get("ANALYSIS_ARTIFACT_DIR", str(default))).absolute()


def _uuid(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise AnalysisError(ErrorCode.ARTIFACT_UNAVAILABLE) from None
    return value


def _directory(parent: int, name: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)


class ArtifactStore:
    def __init__(
        self, engine: Engine, run_id: str, owner: str | None = None,
        generation: int | None = None, *, root: Path | str | None = None,
        clock: Callable[[], datetime] = utcnow,
    ):
        require_postgres(engine)
        self.engine, self.run_id = engine, _uuid(run_id)
        self.owner, self.generation = owner, generation
        self.root = Path(root).absolute() if root is not None else artifact_root()
        self.clock = clock

    def _attempt_directory(self, generation: int, *, create: bool) -> int:
        # Open each child with O_NOFOLLOW. Keeping the descriptor pins the actual
        # directory even if a malicious symlink replaces its pathname later.
        if create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            run_fd = _directory(root_fd, self.run_id, create=create)
            try:
                return _directory(run_fd, f"attempt-{generation}", create=create)
            finally:
                os.close(run_fd)
        finally:
            os.close(root_fd)

    def _register(self, metadata: ArtifactMetadata, relative_path: str) -> None:
        with Session(self.engine) as session, session.begin():
            now = self.clock()
            run = owned_run(session, self.run_id, self.owner, self.generation, now)
            ensure_before_deadline(run, now)
            session.add(AnalysisArtifact(
                **metadata.model_dump(), relative_path=relative_path,
                lease_generation=self.generation,
            ))

    def write(self, data: bytes, *, mime_type: str, purpose: str) -> ArtifactMetadata:
        if self.owner is None or self.generation is None:
            raise AnalysisError(ErrorCode.LEASE_LOST)
        if not isinstance(data, bytes):
            raise TypeError("Artifact data must be bytes.")
        metadata = ArtifactMetadata(
            id=str(uuid4()), run_id=self.run_id, mime_type=mime_type,
            byte_size=len(data), sha256=hashlib.sha256(data).hexdigest(), purpose=purpose,
        )
        # Do not keep this transaction open while writing potentially large files.
        with Session(self.engine) as session, session.begin():
            now = self.clock()
            run = owned_run(session, self.run_id, self.owner, self.generation, now)
            ensure_before_deadline(run, now)
        directory = self._attempt_directory(self.generation, create=True)
        filename = f"{metadata.id}.bin"
        temporary = f".{metadata.id}.partial"
        published = False
        try:
            descriptor = os.open(
                temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory,
            )
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, filename, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
            self._register(metadata, f"{self.run_id}/attempt-{self.generation}/{filename}")
            published = True
        finally:
            for name in (temporary,) if published else (temporary, filename):
                try:
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.close(directory)
        return metadata

    def read(self, artifact_id: str) -> StoredArtifact:
        artifact_id = _uuid(artifact_id)
        with Session(self.engine) as session:
            row = session.get(AnalysisArtifact, artifact_id)
            if row is None or row.run_id != self.run_id:
                raise AnalysisError(ErrorCode.ARTIFACT_UNAVAILABLE)
            metadata = ArtifactMetadata.model_validate({
                key: getattr(row, key) for key in ArtifactMetadata.model_fields
            })
            expected = f"{self.run_id}/attempt-{row.lease_generation}/{artifact_id}.bin"
            if row.relative_path != expected:
                raise AnalysisError(ErrorCode.ARTIFACT_UNAVAILABLE)
            generation = row.lease_generation
        try:
            directory = self._attempt_directory(generation, create=False)
            try:
                descriptor = os.open(f"{artifact_id}.bin", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(descriptor, "rb") as file:
                    if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                        raise AnalysisError(ErrorCode.ARTIFACT_UNAVAILABLE)
                    # A replaced file cannot force an unbounded read.
                    data = file.read(metadata.byte_size + 1)
            finally:
                os.close(directory)
        except OSError:
            raise AnalysisError(ErrorCode.ARTIFACT_UNAVAILABLE) from None
        if len(data) != metadata.byte_size or hashlib.sha256(data).hexdigest() != metadata.sha256:
            raise AnalysisError(ErrorCode.ARTIFACT_CORRUPT)
        return StoredArtifact(metadata=metadata, data=data)
