"""Read-only, versioned demo gate over verified evidence and execution snapshots."""
import hashlib
import json
from factory.models import WorkflowStatus, content_hash
from factory.repositories.document_repository import DocumentRepository
from factory.services._workflow_store import WorkflowStore
from factory.services.approval_service import ApprovalService
from factory.services.coverage_service import CoverageService

POLICY_VERSION = "local-regression-v1"

def canonical_report(report):
    return json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def seal(report):
    report["report_hash"] = hashlib.sha256(canonical_report(report).encode("utf-8")).hexdigest()
    return report

class QualityGateService(WorkflowStore):
    def evaluate(self, workflow_id):
        # A single read transaction prevents mixing a new head with an older journal.
        with self.db.read() as connection:
            current = self.workflows.current(connection, workflow_id)
            checks = []
            def check(key, passed, actual, requirement):
                checks.append(dict(key=key, status="PASS" if passed else "FAIL",
                                   actual=actual, requirement=requirement))
            report = dict(schema_version=1, policy_version=POLICY_VERSION,
                          workflow_id=workflow_id, workflow_revision=current.revision,
                          workflow_hash=content_hash(current), run_id=current.last_run_id,
                          scope="local regression readiness; not production release authorization",
                          checks=checks, metrics={}, unmeasured=[
                              "seeded-gap recall (requires independent labeled benchmark)",
                              "real-model extraction and retrieval accuracy",
                              "manual effort savings and production performance"])
            check("current_evidence", current.status is WorkflowStatus.EVIDENCED,
                  current.status.value, "Current workflow must be EVIDENCED")
            if current.status not in (WorkflowStatus.EXECUTED, WorkflowStatus.EVIDENCED):
                report["verdict"] = "NO-GO"
                report["reason"] = "Current revision has no completed, review-finalized evidence context."
                return seal(report)

            run = self.workflows.get_run(connection, workflow_id, current.last_run_id)
            approved = self.workflows.get(connection, workflow_id, workflow_id, run.workflow_revision)
            selected = tuple(test for test, approval in ApprovalService.ready(approved))
            expected_ids = {(test.test_id, test.revision) for test in selected}
            actual_ids = {(item.test_id, item.test_revision) for item in run.executions}
            check("complete_run", run.status == "completed" and expected_ids == actual_ids,
                  dict(status=run.status, expected=len(expected_ids), recorded=len(actual_ids)),
                  "One execution per approved test in a completed run")
            counts = {status: sum(e.status.value == status for e in run.executions)
                      for status in ("pass", "fail", "error", "skipped")}
            check("execution_results", bool(run.executions) and counts["pass"] == len(run.executions),
                  counts, "Every approved execution must PASS; zero FAIL/ERROR/SKIPPED")
            report["metrics"]["executions"] = counts
            report["approved_revision"] = approved.revision
            report["approved_snapshot_hash"] = content_hash(approved)
            report["run_hash"] = content_hash(run)

            coverage = CoverageService().measure(approved.new_table, approved.new_rules, selected,
                                                 as_of=approved.new_as_of, executions=run.executions)
            report["metrics"]["coverage_mode"] = coverage.mode
            for category in ("rule", "branch", "boundary", "exception"):
                metric = getattr(coverage, category)
                actual = dict(covered=metric.covered, total=metric.total, percent=metric.percent)
                report["metrics"][category + "_coverage"] = actual
                if not metric.total and category != "rule":
                    checks.append(dict(key=category + "_coverage", status="N/A", actual=actual,
                                       requirement="No obligations in this supported category"))
                else:
                    check(category + "_coverage",
                          metric.total > 0 and metric.covered * 100 >= metric.total * 90,
                          actual, "At least 90% of executed-input obligations")
            check("resolved_obligations", not coverage.unresolved_ids, list(coverage.unresolved_ids),
                  "No unresolved bounded-search obligations")
            candidates = tuple(t for t in approved.tests if t.origin.value != "existing")
            selected_ids = {t.test_id for t in selected}
            accepted = sum(t.test_id in selected_ids for t in candidates)
            acceptance = dict(approved=accepted, total=len(candidates),
                              percent=round(100 * accepted / len(candidates), 2) if candidates else None)
            report["metrics"]["candidate_acceptance"] = acceptance
            if candidates:
                check("candidate_acceptance", accepted * 100 >= len(candidates) * 70, acceptance,
                      "At least 70% of current non-existing-origin candidates approved")
            else:
                checks.append(dict(key="candidate_acceptance", status="N/A", actual=acceptance,
                                   requirement="No generated or human-added candidates in this snapshot"))

            # Verify all archived bytes; source-free CLI workflows cannot claim source traceability.
            manifest = {}
            for document in approved.documents:
                stored, data = DocumentRepository().get(connection, workflow_id, document.document_hash)
                if stored != document:
                    from factory.exceptions import ValidationError
                    raise ValidationError("Source manifest differs from archived metadata")
                manifest[stored.document_hash] = stored.document_id
            rules = {(r.rule_id, r.version): r for r in approved.new_rules}
            traced = 0
            for execution in run.executions:
                linked = [rules.get((ref.rule_id, ref.version)) for ref in execution.rules]
                if linked and all(rule is not None and rule.sources and
                                  all(manifest.get(s.document_hash) == s.document_id for s in rule.sources)
                                  for rule in linked):
                    traced += 1
            trace = dict(traced=traced, total=len(run.executions),
                         percent=round(100 * traced / len(run.executions), 2) if run.executions else None)
            report["metrics"]["archived_rule_traceability"] = trace
            check("archived_rule_traceability", bool(run.executions) and traced == len(run.executions),
                  trace, "Every execution links through verified rule snapshots to archived source bytes")

            if current.evidence_id:
                evidence = self.evidence.get(connection, workflow_id, current.evidence_id, 1)
                check("evidence_consistency",
                      evidence.run_id == run.run_id and evidence.executions == run.executions
                      and evidence.tests == selected and evidence.rules == approved.new_rules
                      and evidence.decision_tables == (approved.new_table,),
                      evidence.evidence_id, "Evidence must match the approved snapshot and completed journal")
                report["evidence_id"] = evidence.evidence_id
                report["evidence_hash"] = evidence.fingerprint
            report["verdict"] = "GO" if all(c["status"] in ("PASS", "N/A") for c in checks) else "NO-GO"
            report["reason"] = "All required checks passed." if report["verdict"] == "GO" else "Blocked by: " + ", ".join(
                c["key"] for c in checks if c["status"] == "FAIL")
            return seal(report)
