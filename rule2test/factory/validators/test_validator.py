"""Validate test provenance and revision-bound review before any SUT call."""
from factory.models import ApprovalDecision, SubjectKind, content_hash, ValueKind
from factory.models.common import require
from .rule_validator import FIELDS, validate_money
from factory.exceptions import ValidationError

def input_map(inputs):
    require(type(inputs) is tuple,"Inputs must be a tuple")
    from factory.models.test_case import TestInput
    require(all(type(x) is TestInput for x in inputs),"Expected TestInput")
    require(len({x.field for x in inputs})==len(inputs),"Duplicate input fields")
    require(all(x.field in FIELDS for x in inputs),"Unsupported input field")
    return {x.field:x.value for x in inputs}

def valid_business_value(field,value,currency):
    if field=="age": return value.kind is ValueKind.INTEGER and 0<=value.data<=120
    if value.kind is not ValueKind.MONEY or (currency is not None and value.currency!=currency): return False
    try: validate_money(value);return True
    except ValidationError: return False

def validate_approved_test(test, approval, table, started_at):
    require(test.expected.formula is None,"Expected result must be concrete, not a formula")
    refs=set(row.rule for row in table.rows)
    require(set(test.rules)==refs,"Test must cite all decision-table rule snapshots")
    require(approval.subject_kind is SubjectKind.TEST and approval.decision is ApprovalDecision.APPROVED,"Test is not approved")
    require((approval.subject_id,approval.revision)==(test.test_id,test.revision),"Approval revision mismatch")
    require(approval.content_hash==content_hash(test),"Approval content hash mismatch")
    require(approval.decided_at<=started_at,"Approval cannot be in the future")
    input_map(test.inputs)
