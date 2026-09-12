"""CAS workflow heads, immutable revision history and durable execution journals."""
from datetime import datetime,timezone
from factory.models import content_hash
from factory.models.workflow import Workflow,ExecutionRun
from factory.exceptions import ConflictError,NotFoundError,ValidationError
from ._base import SnapshotRepository

class WorkflowRepository(SnapshotRepository):
    kind="workflow"
    model_type=Workflow
    def identity(self,model):return model.workflow_id,model.revision

    def current(self,c,workflow_id):
        row=c.execute("SELECT revision FROM wf_heads WHERE workflow_id=?",(workflow_id,)).fetchone()
        if not row:raise NotFoundError("Workflow not found")
        return self.get(c,workflow_id,workflow_id,row["revision"])

    def save(self,c,workflow,expected_revision):
        self.put(c,workflow.workflow_id,workflow)
        if expected_revision is None:
            c.execute("INSERT INTO wf_heads VALUES(?,?)",(workflow.workflow_id,workflow.revision))
        else:
            if workflow.revision!=expected_revision+1:raise ConflictError("Workflow revision must increment once")
            cursor=c.execute("UPDATE wf_heads SET revision=? WHERE workflow_id=? AND revision=?",
                             (workflow.revision,workflow.workflow_id,expected_revision))
            if cursor.rowcount!=1:raise ConflictError("Workflow changed; reload before applying this action")

    def event(self,c,workflow,actor,event,detail):
        c.execute("INSERT INTO wf_events(workflow_id,revision,actor,event,detail,created_at) VALUES(?,?,?,?,?,?)",
                  (workflow.workflow_id,workflow.revision,actor,event,detail,datetime.now(timezone.utc).isoformat()))

    def events(self,c,workflow_id):
        self.current(c,workflow_id)
        return tuple(dict(r) for r in c.execute("SELECT * FROM wf_events WHERE workflow_id=? ORDER BY sequence",(workflow_id,)))

    def save_run(self,c,run,*,create=False):
        if create:
            c.execute("INSERT INTO wf_runs VALUES(?,?,?,?)",(run.workflow_id,run.run_id,run.to_json(),content_hash(run)))
        else:
            cursor=c.execute("UPDATE wf_runs SET payload=?,hash=? WHERE workflow_id=? AND run_id=?",
                             (run.to_json(),content_hash(run),run.workflow_id,run.run_id))
            if cursor.rowcount!=1:raise NotFoundError("Run not found")

    def get_run(self,c,workflow_id,run_id):
        row=c.execute("SELECT payload,hash FROM wf_runs WHERE workflow_id=? AND run_id=?",(workflow_id,run_id)).fetchone()
        if not row:raise NotFoundError("Run not found")
        run=ExecutionRun.from_json(row["payload"])
        if content_hash(run)!=row["hash"]:raise ValidationError("Execution journal hash mismatch")
        return run
