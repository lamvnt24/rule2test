from factory.models import Approval
from ._base import SnapshotRepository

class ApprovalRepository(SnapshotRepository):
    kind="approval"
    model_type=Approval
    def identity(self,model):return model.approval_id,1

    def list_for_workflow(self,c,scope):
        rows=c.execute("SELECT payload,hash FROM wf_objects WHERE scope=? AND kind=? ORDER BY rowid",(scope,self.kind))
        return tuple(self.decode(row) for row in rows)
