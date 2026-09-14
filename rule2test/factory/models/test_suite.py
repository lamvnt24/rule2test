"""A test-case file imported on its own: original cells kept verbatim, typed interpretation beside them.

A suite knows nothing about rules. Rows are linked to a rule version later, and only rows whose
interpretation a person confirmed (or that the interpreter read unambiguously) become tests.
"""
from dataclasses import dataclass
from .common import Model,Metadata,require,nonempty
from .import_document import ImportDocument
from .rule import Action
from .test_case import TestInput

COLUMNS=("test_id","title","preconditions","steps","test_data","expected")
ROW_STATUSES=("ready","needs_confirmation","skipped")
INTERPRETATIONS=("pattern","ai","human","none")

@dataclass(frozen=True,kw_only=True)
class SuiteColumn(Model):
    column: str
    letter: str
    header: str
    def __post_init__(self):
        super().__post_init__()
        require(self.column in COLUMNS,"Unknown suite column")
        require(self.letter.isalpha() and self.letter.isupper(),"Column letter must be uppercase letters")

@dataclass(frozen=True,kw_only=True)
class SuiteCell(Model):
    column: str
    header: str
    cell: str
    text: str
    def __post_init__(self):
        super().__post_init__();require(self.column in COLUMNS,"Unknown suite column");nonempty(self.cell,"cell")

@dataclass(frozen=True,kw_only=True)
class SuiteRow(Model):
    row_id: str
    row_number: int
    title: str
    cells: tuple[SuiteCell,...]
    status: str
    interpretation: str
    inputs: tuple[TestInput,...] = ()
    expected: Action | None = None
    notes: tuple[str,...] = ()
    questions: tuple[str,...] = ()
    def __post_init__(self):
        super().__post_init__();nonempty(self.row_id,"row_id");nonempty(self.title,"title")
        require(self.row_number>0,"Row number is one-based")
        require(self.status in ROW_STATUSES,"Unknown row status")
        require(self.interpretation in INTERPRETATIONS,"Unknown interpretation source")
        require(len({c.column for c in self.cells})==len(self.cells),"Duplicate cell column")
        require(len({x.field for x in self.inputs})==len(self.inputs),"Duplicate input field")
        if self.status=="ready":
            require(bool(self.inputs) and self.expected is not None and not self.questions,"A ready row needs typed inputs, an expected outcome and no open question")
            require(self.interpretation!="none","A ready row records how it was interpreted")
        if self.status=="needs_confirmation":require(bool(self.questions),"An unconfirmed row states what is unclear")
    def cell(self,column):
        return next((c for c in self.cells if c.column==column),None)

@dataclass(frozen=True,kw_only=True)
class TestSuite(Model):
    suite_id: str
    title: str
    document: ImportDocument
    sheet: str
    columns: tuple[SuiteColumn,...]
    rows: tuple[SuiteRow,...]
    interpreter: str
    metadata: Metadata
    def __post_init__(self):
        super().__post_init__();nonempty(self.suite_id,"suite_id");nonempty(self.title,"title");nonempty(self.sheet,"sheet")
        nonempty(self.interpreter,"interpreter")
        require(bool(self.rows),"A suite needs at least one row")
        require(len({r.row_id for r in self.rows})==len(self.rows),"Duplicate row ID")
        require(len({r.row_number for r in self.rows})==len(self.rows),"Duplicate row number")
        require(len({c.column for c in self.columns})==len(self.columns),"Duplicate mapped column")
        require(len({c.letter for c in self.columns})==len(self.columns),"One sheet column cannot feed two fields")
    def counts(self):
        return {status:sum(r.status==status for r in self.rows) for status in ROW_STATUSES}

@dataclass(frozen=True,kw_only=True)
class ExcludedRow(Model):
    row_id: str
    title: str
    reason: str
    def __post_init__(self):
        super().__post_init__();nonempty(self.row_id,"row_id");nonempty(self.reason,"reason")

@dataclass(frozen=True,kw_only=True)
class SuiteLink(Model):
    """Which suite rows became existing tests of which workflow, and why the others did not."""
    workflow_id: str
    suite_id: str
    proposal_id: str
    proposal_hash: str
    linked: tuple[str,...]
    excluded: tuple[ExcludedRow,...]
    metadata: Metadata
    def __post_init__(self):
        super().__post_init__()
        for key in ("workflow_id","suite_id","proposal_id"):nonempty(getattr(self,key),key)
        require(len(set(self.linked))==len(self.linked),"Duplicate linked row")
