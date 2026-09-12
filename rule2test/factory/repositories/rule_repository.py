from factory.models import Rule,DecisionTable
from ._base import SnapshotRepository

class RuleRepository(SnapshotRepository):
    kind="rule"
    model_type=Rule
    def identity(self,model):return model.rule_id,model.version

class DecisionTableRepository(SnapshotRepository):
    kind="decision_table"
    model_type=DecisionTable
    def identity(self,model):return model.table_id,model.version
