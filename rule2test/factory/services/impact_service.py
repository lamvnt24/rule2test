"""Deterministic dependency and behavior impact, without semantic retrieval claims."""
from factory.models.analysis import ImpactRecord
from factory.engines.oracle_engine import OracleEngine
from factory.exceptions import ValidationError,ConflictError
from factory.validators.rule_validator import validate_table
from ._support import unique_tests
from .rule_delta_service import RuleDeltaService

class ImpactService:
    def analyze(self,old_table,old_rules,new_table,new_rules,tests,*,old_as_of=None,new_as_of=None):
        unique_tests(tests)
        validate_table(old_table,old_rules,old_as_of);validate_table(new_table,new_rules,new_as_of)
        delta=RuleDeltaService().compare(old_rules,new_rules)
        changed={(d.after or d.before).rule_id for d in delta.deltas}
        table_changed=(old_table.hit_policy!=new_table.hit_policy or old_table.default_action!=new_table.default_action
                       or tuple(r.rule.rule_id for r in old_table.rows)!=tuple(r.rule.rule_id for r in new_table.rows)
                       or old_as_of!=new_as_of)
        scope={r.rule_id for r in old_rules+new_rules};old_ids={r.rule_id for r in old_rules};new_ids={r.rule_id for r in new_rules}
        oracle=OracleEngine();records=[]
        for test in sorted(tests,key=lambda t:(t.test_id,t.revision)):
            linked={r.rule_id for r in test.rules}
            related=bool(linked&changed) or (table_changed and bool(linked&scope))
            old_result=new_result=None
            if not linked&scope:
                status="unrelated";reason="No rule-ID dependency in either table"
            elif not linked<=old_ids or not linked<=new_ids:
                status="unknown";reason="Rule dependency added or removed; explicit test remapping required"
            else:
                try:
                    old_result=oracle.evaluate(old_table,old_rules,test.inputs,as_of=old_as_of)
                    new_result=oracle.evaluate(new_table,new_rules,test.inputs,as_of=new_as_of)
                    status="changed" if old_result!=new_result else ("unchanged" if related else "unaffected")
                    reason="Compared deterministic outcomes across table versions"
                except (ValidationError,ConflictError):
                    status="unknown";reason="Input or decision-table conflict requires review"
            records.append(ImpactRecord(test_id=test.test_id,revision=test.revision,related=related,status=status,
                old_expected=old_result,new_expected=new_result,
                expected_is_stale=(test.expected!=new_result) if new_result else None,reason=reason))
        return tuple(records)
