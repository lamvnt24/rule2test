"""Archive exact source bytes in the same transaction as the imported workflow."""
import hashlib
from factory.models.import_document import ImportDocument
from factory.models.common import require
from factory.exceptions import NotFoundError,ConflictError

class DocumentRepository:
    table="wf_source_documents";key="workflow_id"

    @staticmethod
    def validate(document,data):
        require(type(document) is ImportDocument and type(data) is bytes,"Expected document metadata and bytes")
        require(len(data)==document.size_bytes and hashlib.sha256(data).hexdigest()==document.document_hash,"Source document hash/size mismatch")

    def put(self,c,scope,document,data):
        self.validate(document,data)
        row=c.execute(f"SELECT metadata,data FROM {self.table} WHERE {self.key}=? AND document_hash=?",
                      (scope,document.document_hash)).fetchone()
        if row:
            if row["metadata"]!=document.to_json() or row["data"]!=data:raise ConflictError("Immutable source document conflict")
            return
        c.execute(f"INSERT INTO {self.table} VALUES(?,?,?,?)",(scope,document.document_hash,document.to_json(),data))

    def get(self,c,scope,document_hash):
        row=c.execute(f"SELECT metadata,data FROM {self.table} WHERE {self.key}=? AND document_hash=?",
                      (scope,document_hash)).fetchone()
        if row is None:raise NotFoundError("Source document not found in workflow")
        document=ImportDocument.from_json(row["metadata"])
        require(document.document_hash==document_hash,"Source document identity mismatch")
        self.validate(document,row["data"])
        return document,row["data"]

class ArchiveRepository(DocumentRepository):
    """The same archive contract for objects that exist before any workflow, such as a test-case file."""
    table="wf_documents";key="scope"
