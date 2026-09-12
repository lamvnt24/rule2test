"""Added, removed and modified rule snapshots."""
from dataclasses import dataclass
from enum import Enum
from .common import Model, require, nonempty
from .rule import Rule

class DeltaKind(str,Enum):
    ADDED="added"
    REMOVED="removed"
    MODIFIED="modified"

@dataclass(frozen=True,kw_only=True)
class RuleDelta(Model):
    delta_id: str
    kind: DeltaKind
    before: Rule | None
    after: Rule | None
    changed_fields: tuple[str,...] = ()
    explanation: str = ""
    def __post_init__(self):
        super().__post_init__();nonempty(self.delta_id,"delta_id")
        if self.kind is DeltaKind.ADDED: require(self.before is None and self.after is not None,"Added delta requires only after")
        elif self.kind is DeltaKind.REMOVED: require(self.before is not None and self.after is None,"Removed delta requires only before")
        else:
            require(self.before is not None and self.after is not None,"Modified delta requires both snapshots")
            require(self.before.rule_id==self.after.rule_id,"Modified snapshots must share rule ID")
            require(self.after.version>self.before.version,"Modified version must increase")
            require(bool(self.changed_fields),"Modified delta requires changed fields")
        allowed={"title","conditions","action","sources","effective_from","effective_to"}
        require(len(set(self.changed_fields))==len(self.changed_fields),"Duplicate changed fields")
        require(set(self.changed_fields)<=allowed,"Unsupported changed field")
        if self.kind is DeltaKind.MODIFIED:
            actual={k for k in allowed if getattr(self.before,k)!=getattr(self.after,k)}
            require(actual==set(self.changed_fields),"Changed fields must match snapshots exactly")
        else: require(not self.changed_fields,"Added/removed deltas use full snapshots")
