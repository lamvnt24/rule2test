"""Serializable analysis results; candidates do not imply approval."""
from dataclasses import dataclass
from enum import Enum
from datetime import date
from decimal import Decimal
from .common import Model, RuleReference
from .rule import Action
from .rule_delta import RuleDelta
from .test_case import TestCase, TestInput

@dataclass(frozen=True, kw_only=True)
class DeltaAnalysis(Model):
    deltas: tuple[RuleDelta, ...]
    presentation_only_rule_ids: tuple[str, ...]

@dataclass(frozen=True, kw_only=True)
class ImpactRecord(Model):
    test_id: str
    revision: int
    related: bool
    status: str
    old_expected: Action | None
    new_expected: Action | None
    expected_is_stale: bool | None
    reason: str

@dataclass(frozen=True, kw_only=True)
class Obligation(Model):
    obligation_id: str
    category: str
    rule_id: str | None
    row_id: str | None
    label: str
    inputs: tuple[TestInput, ...] | None
    unresolved_reason: str | None = None

@dataclass(frozen=True, kw_only=True)
class GapAnalysis(Model):
    evaluation_date: date | None
    money_step: Decimal
    table_hash: str
    obligations: tuple[Obligation, ...]
    covered_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    unresolved_ids: tuple[str, ...]
    search_size: int

@dataclass(frozen=True, kw_only=True)
class GenerationResult(Model):
    candidates: tuple[TestCase, ...]
    unresolved_ids: tuple[str, ...]

@dataclass(frozen=True, kw_only=True)
class CoverageMetric(Model):
    covered: int
    total: int
    @property
    def percent(self):
        return round(100*self.covered/self.total, 2) if self.total else None

@dataclass(frozen=True, kw_only=True)
class CoverageReport(Model):
    mode: str
    rule: CoverageMetric
    branch: CoverageMetric
    boundary: CoverageMetric
    exception: CoverageMetric
    covered_ids: tuple[str, ...]
    uncovered_ids: tuple[str, ...]
    unresolved_ids: tuple[str, ...]

class MutationStatus(str, Enum):
    KILLED="killed"
    SURVIVED="survived"
    INVALID="invalid"

@dataclass(frozen=True, kw_only=True)
class MutationResult(Model):
    mutation_id: str
    rule_id: str | None
    description: str
    status: MutationStatus
    witnesses: tuple[str, ...]
    reason: str | None = None

@dataclass(frozen=True, kw_only=True)
class MutationReport(Model):
    results: tuple[MutationResult, ...]
    test_count: int
    @property
    def score(self):
        valid=[r for r in self.results if r.status is not MutationStatus.INVALID]
        return round(100*sum(r.status is MutationStatus.KILLED for r in valid)/len(valid),2) if valid and self.test_count else None
