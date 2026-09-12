"""Separate designed-input coverage from verified execution coverage."""
from factory.models import ExecutionStatus,content_hash
from factory.models.common import require
from factory.models.analysis import CoverageMetric,CoverageReport
from ._support import SearchContext,unique_tests,references
from .gap_service import GapService

class CoverageService:
    def __init__(self,**search_options):
        self.search_options=search_options

    def measure(self,table,rules,tests,*,as_of=None,executions=None):
        unique_tests(tests)
        mode="designed inputs"
        selected=tests
        if executions is not None:
            mode="executed inputs"
            lookup={(t.test_id,t.revision):t for t in tests};exercised=set()
            for execution in executions:
                key=(execution.test_id,execution.test_revision)
                require(key in lookup,"Execution references unknown test")
                require(execution.test_hash==content_hash(lookup[key]),"Execution test hash mismatch")
                require(set(lookup[key].rules)==set(references(rules)),"Executed tests must reference current rule snapshots")
                require(execution.decision_table_hash==content_hash(table) and execution.evaluation_date==as_of,"Execution context mismatch")
                require(execution.expected==lookup[key].expected and execution.rules==lookup[key].rules,"Execution differs from test")
                if execution.status in (ExecutionStatus.PASS,ExecutionStatus.FAIL):exercised.add(key)
            selected=tuple(t for t in tests if (t.test_id,t.revision) in exercised)
        gaps=GapService(**self.search_options).analyze(table,rules,selected,as_of=as_of)
        ctx=SearchContext(table,rules,as_of=as_of,**self.search_options)
        active_ids={r.rule.rule_id for r in ctx.active}
        covered_rules={o.rule_id for o in gaps.obligations if o.category=="branch" and o.rule_id is not None and o.obligation_id in gaps.covered_ids}
        def metric(category):
            items=[o for o in gaps.obligations if o.category==category]
            return CoverageMetric(covered=sum(o.obligation_id in gaps.covered_ids for o in items),total=len(items))
        return CoverageReport(mode=mode,rule=CoverageMetric(covered=len(covered_rules),total=len(active_ids)),
            branch=metric("branch"),boundary=metric("boundary"),exception=metric("exception"),
            covered_ids=gaps.covered_ids,uncovered_ids=gaps.missing_ids,unresolved_ids=gaps.unresolved_ids)
