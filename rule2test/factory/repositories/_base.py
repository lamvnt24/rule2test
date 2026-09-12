"""Immutable object snapshots, namespaced by workflow."""
from factory.models import content_hash
from factory.exceptions import ConflictError,NotFoundError,ValidationError

class SnapshotRepository:
    kind=""
    model_type=None
    def identity(self,model):raise NotImplementedError

    def put(self,c,scope,model):
        entity_id,revision=self.identity(model)
        row=c.execute("SELECT hash FROM wf_objects WHERE scope=? AND kind=? AND entity_id=? AND revision=?",
                      (scope,self.kind,entity_id,revision)).fetchone()
        fingerprint=content_hash(model)
        if row:
            if row["hash"]!=fingerprint:raise ConflictError("Immutable snapshot already exists with different content")
            return
        c.execute("INSERT INTO wf_objects VALUES(?,?,?,?,?,?)",(scope,self.kind,entity_id,revision,model.to_json(),fingerprint))

    def get(self,c,scope,entity_id,revision):
        row=c.execute("SELECT payload,hash FROM wf_objects WHERE scope=? AND kind=? AND entity_id=? AND revision=?",
                      (scope,self.kind,entity_id,revision)).fetchone()
        if not row:raise NotFoundError(self.kind+" snapshot not found")
        return self.decode(row)

    def decode(self,row):
        model=self.model_type.from_json(row["payload"])
        if content_hash(model)!=row["hash"]:raise ValidationError("Stored "+self.kind+" snapshot hash mismatch")
        return model

    def history(self,c,scope,entity_id):
        rows=c.execute("SELECT payload,hash FROM wf_objects WHERE scope=? AND kind=? AND entity_id=? ORDER BY revision",
                       (scope,self.kind,entity_id))
        return tuple(self.decode(row) for row in rows)
