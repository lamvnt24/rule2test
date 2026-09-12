"""Explicit decision-table ordering and hit policy; evaluation is phase 2."""
from dataclasses import dataclass
from enum import Enum
from .common import Model, RuleReference, require, nonempty
from .rule import Condition, Action

class HitPolicy(str,Enum):
    UNIQUE="unique"
    FIRST="first"
    COLLECT="collect"

@dataclass(frozen=True,kw_only=True)
class DecisionRow(Model):
    row_id: str
    conditions: tuple[Condition,...]
    action: Action
    rule: RuleReference
    def __post_init__(self):
        super().__post_init__();nonempty(self.row_id,"row_id")
        require(bool(self.conditions),"Row requires conditions")

@dataclass(frozen=True,kw_only=True)
class DecisionTable(Model):
    table_id: str
    version: int
    hit_policy: HitPolicy
    rows: tuple[DecisionRow,...]
    default_action: Action
    def __post_init__(self):
        super().__post_init__();nonempty(self.table_id,"table_id");require(self.version>0,"Version must be positive")
        require(bool(self.rows),"Decision table requires rows")
        require(len({r.row_id for r in self.rows})==len(self.rows),"Duplicate row ID")
