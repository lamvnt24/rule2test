"""Import a test-case file on its own: inspect, interpret, let a person confirm, then archive."""
from datetime import datetime,timezone
from decimal import Decimal
from uuid import uuid4
from factory.models import Metadata,Value,ValueKind,TestInput,Action,Outcome
from factory.models.common import require,nonempty
from factory.models.test_suite import TestSuite,SuiteRow,SuiteCell,SuiteColumn,COLUMNS
from factory.parsers.common import document
from factory.parsers.testcase_parser import inspect as inspect_file,extract_rows,MEDIA
from factory.repositories.document_repository import ArchiveRepository
from factory.repositories.suite_repository import SuiteRepository,SCOPE
from factory.validators.rule_validator import FIELDS
from factory.validators.test_validator import input_map
from .testcase_interpreter import interpret,INTERPRETER
from .text_patterns import parse_number,fmt_inputs,fmt_action
from pathlib import Path

def human_value(field,raw,currency):
    """A value a person typed into the confirmation form. Empty/missing/quoted text are robustness inputs."""
    require(field in FIELDS,"Unsupported field: "+str(field))
    text=str(raw if raw is not None else "").strip()
    lowered=text.casefold()
    if lowered in ("empty","null","blank"):return Value(kind=ValueKind.NULL)
    if lowered in ("missing","omitted","absent"):return Value(kind=ValueKind.MISSING)
    if len(text)>=2 and text[0]==text[-1] and text[0] in "\"'":return Value(kind=ValueKind.TEXT,data=text[1:-1])
    nonempty(text,"value")
    if field=="age":
        require(text.lstrip("-").isdigit(),"Age must be a whole number, empty, missing or quoted text")
        return Value(kind=ValueKind.INTEGER,data=int(text))
    try:amount=parse_number(text)
    except ValueError as exc:raise ValueError("Claim amount must be a number") from exc
    require(type(currency) is str and len(currency.strip())==3,"Money needs a three-letter currency such as VND")
    return Value(kind=ValueKind.MONEY,data=amount,currency=currency.strip().upper())

def human_expected(payload):
    require(type(payload) is dict and "outcome" in payload,"Expected outcome is required")
    outcome=Outcome(str(payload["outcome"]).strip().lower())
    if outcome is not Outcome.PAYOUT:return Action(outcome=outcome)
    amount=payload.get("amount");currency=payload.get("currency") or "VND"
    require(amount not in (None,""),"A payout needs an amount")
    return Action(outcome=outcome,amount=Value(kind=ValueKind.MONEY,data=parse_number(str(amount)),currency=str(currency).strip().upper()))

def interpreted_rows(data,name,sheet,mapping,header_row=None):
    """Every data row read by the pattern interpreter; nothing is persisted."""
    rows,columns=extract_rows(data,name,sheet,mapping,header_row)
    result=[];seen={}
    for raw in rows:
        cells=raw["cells"];texts={column:cell["text"] for column,cell in cells.items()}
        inputs,expected,status,notes,questions=interpret(texts)
        row_id=texts.get("test_id","").strip() or "ROW-"+str(raw["row_number"])
        if row_id in seen:
            notes=notes+("Duplicate test ID "+row_id+"; row "+str(raw["row_number"])+" was renamed.",)
            row_id=row_id+"@"+str(raw["row_number"])
        seen[row_id]=raw["row_number"]
        title=texts.get("title","").strip() or row_id
        result.append(SuiteRow(row_id=row_id,row_number=raw["row_number"],title=title,
            cells=tuple(SuiteCell(**cells[column]) for column in COLUMNS if column in cells),
            status=status,interpretation="pattern" if inputs or expected else "none",
            inputs=inputs,expected=expected,notes=notes,questions=questions))
    return tuple(result),tuple(SuiteColumn(**column) for column in columns)

def apply_resolutions(rows,resolutions):
    """A person's answers to the interpreter's questions, or corrections of its readings."""
    require(type(resolutions) is list and len(resolutions)<=5000,"Resolutions must be a list")
    by_number={row.row_number:row for row in rows}
    updated=dict(by_number)
    for item in resolutions:
        require(type(item) is dict and type(item.get("row_number")) is int and item["row_number"] in by_number,"Resolution must name an imported row")
        row=by_number[item["row_number"]]
        if item.get("skip"):
            updated[row.row_number]=SuiteRow(row_id=row.row_id,row_number=row.row_number,title=row.title,cells=row.cells,status="skipped",
                interpretation="human",inputs=(),expected=None,notes=row.notes+("Skipped by the reviewer.",),questions=row.questions)
            continue
        values=item.get("inputs")
        require(type(values) is list and 0<len(values)<=2 and all(type(v) is dict and set(v)<={"field","value","currency"} for v in values),"Give one or two inputs as field/value/currency")
        inputs=tuple(TestInput(field=str(v.get("field","")),value=human_value(v.get("field"),v.get("value"),v.get("currency"))) for v in values)
        input_map(inputs)
        expected=human_expected(item.get("expected"))
        updated[row.row_number]=SuiteRow(row_id=row.row_id,row_number=row.row_number,title=row.title,cells=row.cells,status="ready",
            interpretation="human",inputs=inputs,expected=expected,
            notes=row.notes+("Confirmed by the reviewer: "+fmt_inputs(inputs)+" → "+fmt_action(expected),))
    return tuple(updated[number] for number in sorted(updated))

class SuiteService:
    def __init__(self,database):
        self.db=database;self.suites=SuiteRepository();self.archive=ArchiveRepository()

    @staticmethod
    def inspect(data,name):return inspect_file(data,name)

    @staticmethod
    def preview(data,name,sheet,mapping,header_row=None):
        rows,columns=interpreted_rows(data,name,sheet,mapping,header_row)
        return rows,columns

    def create(self,data,name,sheet,mapping,*,actor,resolutions=(),header_row=None):
        nonempty(actor,"actor")
        rows,columns=interpreted_rows(data,name,sheet,mapping,header_row)
        rows=apply_resolutions(rows,list(resolutions))
        doc=document(data,name,MEDIA[Path(name).suffix.lower()])
        suite=TestSuite(suite_id=str(uuid4()),title=name,document=doc,sheet=sheet,columns=columns,rows=rows,interpreter=INTERPRETER,
            metadata=Metadata(created_at=datetime.now(timezone.utc),created_by=actor))
        with self.db.transaction() as c:
            self.suites.put(c,SCOPE,suite)
            self.archive.put(c,suite.suite_id,doc,data)
        return suite

    def get(self,suite_id):
        with self.db.read() as c:return self.suites.get(c,SCOPE,suite_id,1)

    def list(self,limit=100):
        with self.db.read() as c:
            rows=c.execute("SELECT payload,hash FROM wf_objects WHERE scope=? AND kind=? ORDER BY rowid DESC LIMIT ?",(SCOPE,self.suites.kind,limit))
            return [self.suites.decode(row) for row in rows]

    def source(self,suite_id):
        with self.db.read() as c:
            suite=self.suites.get(c,SCOPE,suite_id,1)
            return self.archive.get(c,suite_id,suite.document.document_hash)

def summary(suite):
    counts=suite.counts()
    return dict(suite_id=suite.suite_id,title=suite.title,sheet=suite.sheet,rows=len(suite.rows),ready=counts["ready"],
        needs_confirmation=counts["needs_confirmation"],skipped=counts["skipped"],interpreter=suite.interpreter,
        created_by=suite.metadata.created_by,created_at=suite.metadata.created_at.isoformat(),document_hash=suite.document.document_hash)
