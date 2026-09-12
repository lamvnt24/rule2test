"""Deterministic candidate generation; creates no approvals and mutates no tests."""
from dataclasses import replace
from factory.models import TestCase,TestKind,TestOrigin,content_hash
from factory.models.common import require
from factory.models.analysis import GenerationResult
from factory.engines.oracle_engine import OracleEngine
from factory.validators.rule_validator import validate_table
from ._support import stable_id,inputs_key,references,unique_tests
from .gap_service import GapService

class GenerationService:
    def generate(self,table,rules,gaps,*,metadata,as_of=None):
        validate_table(table,rules,as_of)
        require(gaps.table_hash==content_hash(table),"Gap analysis belongs to a different table")
        require(gaps.evaluation_date==as_of,"Gap analysis evaluation date mismatch")
        grouped={}
        for obligation in gaps.obligations:
            if obligation.obligation_id in gaps.missing_ids and obligation.inputs is not None:
                grouped.setdefault(inputs_key(obligation.inputs),[]).append(obligation)
        oracle=OracleEngine();candidates=[]
        for key,items in sorted(grouped.items(),key=lambda pair:str(pair[0])):
            inputs=tuple(sorted(items[0].inputs,key=lambda x:x.field))
            expected=oracle.evaluate(table,rules,inputs,as_of=as_of)
            identifier=stable_id("GEN-",[content_hash(table),str(as_of),key])
            kind=TestKind.EXCEPTION if any(o.category=="exception" for o in items) else (TestKind.BOUNDARY if any(o.category=="boundary" for o in items) else TestKind.POSITIVE)
            candidates.append(TestCase(test_id=identifier,revision=1,title="Cover "+items[0].label,inputs=inputs,
                expected=expected,kind=kind,origin=TestOrigin.DETERMINISTIC,rules=references(rules),
                rationale="Requires QA review. Covers: "+"; ".join(o.label for o in items),
                metadata=metadata,obligation_ids=tuple(sorted(o.obligation_id for o in items))))
        return GenerationResult(candidates=tuple(candidates),unresolved_ids=gaps.unresolved_ids)

    def rebase(self,table,rules,tests,*,metadata,as_of=None):
        """Explicit revision proposals for existing tests; approval must be obtained again."""
        validate_table(table,rules,as_of);unique_tests(tests)
        oracle=OracleEngine();scope={r.rule_id for r in rules};proposals=[]
        for test in sorted(tests,key=lambda t:(t.test_id,t.revision)):
            require({r.rule_id for r in test.rules}<=scope,"Removed/unknown rule requires explicit remapping")
            expected=oracle.evaluate(table,rules,test.inputs,as_of=as_of)
            proposals.append(replace(test,revision=test.revision+1,rules=references(rules),expected=expected,
                origin=TestOrigin.DETERMINISTIC,metadata=metadata,obligation_ids=(),
                rationale="Revision proposal; previous approval is invalid. "+test.rationale))
        return tuple(proposals)
