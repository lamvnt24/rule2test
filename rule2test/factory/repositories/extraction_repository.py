"""Use the existing immutable object store; no workflow schema migration is needed."""
from ._base import SnapshotRepository
from factory.models.extraction import ExtractionProposal,ExtractionReview,ExtractionPromotion

class ProposalRepository(SnapshotRepository):
    kind="extraction_proposal"
    model_type=ExtractionProposal
    def identity(self,model):return model.proposal_id,1

class ExtractionReviewRepository(SnapshotRepository):
    kind="extraction_review"
    model_type=ExtractionReview
    def identity(self,model):return model.proposal_id,1

class PromotionRepository(SnapshotRepository):
    kind="extraction_promotion"
    model_type=ExtractionPromotion
    def identity(self,model):return model.proposal_id,1
