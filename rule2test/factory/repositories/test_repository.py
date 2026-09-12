from factory.models import TestCase
from ._base import SnapshotRepository

class TestRepository(SnapshotRepository):
    kind="test"
    model_type=TestCase
    def identity(self,model):return model.test_id,model.revision
