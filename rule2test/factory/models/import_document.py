"""Original document metadata persisted alongside an imported workflow."""
from dataclasses import dataclass
from .common import Model,require,nonempty,sha256

@dataclass(frozen=True,kw_only=True)
class ImportDocument(Model):
    document_id: str
    document_hash: str
    media_type: str
    size_bytes: int
    def __post_init__(self):
        super().__post_init__();nonempty(self.document_id,"document_id");sha256(self.document_hash)
        require(self.media_type in ("text/plain","text/csv","application/json","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),"Unsupported document type")
        require(0<self.size_bytes<=10*1024*1024,"Document must be 1 byte..10 MiB")