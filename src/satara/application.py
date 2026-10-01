from satara.common.models import FrozenModel
from satara.domain import Archive, ArchiveFile


class FileObject(FrozenModel):
    def as_entity(self) -> ArchiveFile:
        ...

class CompressFilesCommand(FrozenModel):
    files: set

class ArchiverService:
    async def compress_files(self, command: CompressFilesCommand):
        archive = Archive.create_empty()
        for file in command.files:
            archive.add_file(file.as_entity())
