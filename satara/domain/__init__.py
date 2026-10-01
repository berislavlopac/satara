from satara.common.models import Entity, FrozenModel, IDModel


class ArchiveFileChecksum(FrozenModel):
    """File checksum of an uploaded file."""

    value: int

    def __hash__(self) -> int:
        return self.value


class ArchiveFile(Entity):
    checksum: ArchiveFileChecksum
    filename: str
    mimetype: str
    size: int

    def __hash__(self) -> int:
        return hash(self.checksum)


class ArchiveID(IDModel):
    """Value object of the archive ID."""


class Archive(Entity):
    archive_id: ArchiveID
    files: set[ArchiveFile]

    @classmethod
    def create_empty(cls):
        return cls(archive_id=ArchiveID.generate(), files=set())

    def add_file(self, file: ArchiveFile):
        self.files.add(file)
