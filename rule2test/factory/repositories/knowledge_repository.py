"""Versioned corpus and test suggestions use the existing immutable object store."""
from ._base import SnapshotRepository
from factory.models.knowledge import KnowledgeIndex,RetrievalBatch
class KnowledgeRepository(SnapshotRepository):
    kind="knowledge_index"
    model_type=KnowledgeIndex
    def identity(self,model):return model.index_id,1
class RetrievalBatchRepository(SnapshotRepository):
    kind="retrieval_batch"
    model_type=RetrievalBatch
    def identity(self,model):return model.batch_id,1
