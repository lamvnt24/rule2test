"""Versioned test candidates and typed test inputs, including invalid cases."""
from dataclasses import dataclass
from enum import Enum
from .common import Model, Value, RuleReference, SourceReference, Metadata, require, nonempty
from .rule import Action

class TestKind(str,Enum):
    POSITIVE="positive"
    NEGATIVE="negative"
    BOUNDARY="boundary"
    EXCEPTION="exception"
class TestOrigin(str,Enum):
    EXISTING="existing"
    DETERMINISTIC="deterministic"
    LLM="llm"
    HUMAN="human"

@dataclass(frozen=True,kw_only=True)
class TestInput(Model):
    field: str
    value: Value
    def __post_init__(self):
        super().__post_init__();nonempty(self.field,"field")

@dataclass(frozen=True,kw_only=True)
class TestCase(Model):
    test_id: str
    revision: int
    title: str
    inputs: tuple[TestInput,...]
    expected: Action
    kind: TestKind
    origin: TestOrigin
    rules: tuple[RuleReference,...]
    rationale: str
    metadata: Metadata
    obligation_ids: tuple[str,...] = ()
    sources: tuple[SourceReference,...] = ()
    def to_dict(self):
        result=super().to_dict()
        if not self.sources:result.pop("sources")
        return result
    def __post_init__(self):
        super().__post_init__();nonempty(self.test_id,"test_id");nonempty(self.title,"title");nonempty(self.rationale,"rationale")
        require(self.revision>0,"Revision must be positive")
        require(bool(self.inputs),"Test requires inputs")
        require(len({v.field for v in self.inputs})==len(self.inputs),"Duplicate input field")
        require(bool(self.rules) and len({r.rule_id for r in self.rules})==len(self.rules),"Test requires unique rule references")
        require(len(set(self.obligation_ids))==len(self.obligation_ids),"Duplicate obligation")
        for value in self.obligation_ids: nonempty(value,"obligation ID")