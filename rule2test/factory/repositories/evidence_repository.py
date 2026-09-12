from factory.models import Evidence
from ._base import SnapshotRepository

class EvidenceRepository(SnapshotRepository):
    kind="evidence"
    model_type=Evidence
    def identity(self,model):return model.evidence_id,1
