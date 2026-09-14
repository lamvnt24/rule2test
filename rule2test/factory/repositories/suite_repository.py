"""Test-case suites and their workflow links live in the immutable object store under one scope."""
from ._base import SnapshotRepository
from factory.models.test_suite import TestSuite,SuiteLink

SCOPE="suites"

class SuiteRepository(SnapshotRepository):
    kind="test_suite"
    model_type=TestSuite
    def identity(self,model):return model.suite_id,1

class SuiteLinkRepository(SnapshotRepository):
    kind="suite_link"
    model_type=SuiteLink
    def identity(self,model):return model.workflow_id,1
