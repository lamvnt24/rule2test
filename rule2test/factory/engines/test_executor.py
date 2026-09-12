"""Approved test execution. Recompute expected for consistency, never overwrite it."""
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4
from factory.models import Action, Execution, ExecutionStatus, content_hash
from factory.models.common import require, nonempty
from factory.engines.oracle_engine import OracleEngine
from factory.validators.test_validator import validate_approved_test
from factory.exceptions import ProviderError

class TestExecutor:
    def __init__(self,adapter,*,timeout_seconds=10):
        require(type(timeout_seconds) in (int,float) and 0<timeout_seconds<=300,"Timeout must be 0..300 seconds")
        self.adapter=adapter;self.timeout_seconds=timeout_seconds
        self.oracle=OracleEngine()
    def execute(self,test,approval,table,rules,*,run_id,as_of=None):
        nonempty(run_id,"run_id")
        started=datetime.now(timezone.utc)
        validate_approved_test(test,approval,table,started)
        expected=self.oracle.evaluate(table,rules,test.inputs,as_of=as_of)
        require(expected==test.expected,"Approved expected differs from oracle; review a new test revision")
        # Validation failures above abort before any SUT side effect.
        error=None;actual=None
        clock=monotonic()
        try:
            actual=self.adapter.execute(test.inputs,timeout_seconds=self.timeout_seconds)
            if monotonic()-clock>self.timeout_seconds: raise ProviderError("SUT exceeded execution time budget")
            if type(actual) is not Action or actual.formula is not None: raise ProviderError("SUT returned invalid actual")
            status=ExecutionStatus.PASS if actual==test.expected else ExecutionStatus.FAIL
        except (ProviderError,TimeoutError,OSError):
            # Do not copy arbitrary upstream exception text (may contain credentials).
            error="SUT unavailable, timed out, or returned an invalid response"
            actual=None;status=ExecutionStatus.ERROR
        return Execution(execution_id=str(uuid4()),run_id=run_id,test_id=test.test_id,test_revision=test.revision,
            test_hash=content_hash(test),rules=test.rules,approval_id=approval.approval_id,
            expected=test.expected,actual=actual,status=status,adapter=self.adapter.name,
            started_at=started,finished_at=datetime.now(timezone.utc),error=error,
            decision_table_hash=content_hash(table),evaluation_date=as_of)
