"""Import diagnostics and shared input limits."""
import json,hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from factory.exceptions import ValidationError
from datetime import date
from factory.models import SourceReference,DecisionTable,Rule,TestCase
from factory.models.import_document import ImportDocument

MAX_BYTES=10*1024*1024
MAX_ROWS=5000

@dataclass(frozen=True)
class ImportIssue:
    document: str
    message: str
    sheet: str | None = None
    cell: str | None = None
    pointer: str | None = None
    def to_dict(self):return dict(document=self.document,sheet=self.sheet,cell=self.cell,json_pointer=self.pointer,message=self.message)

class ImportFailure(ValidationError):
    def __init__(self,issues):
        self.issues=tuple(issues)
        super().__init__("; ".join(f"{i.document}:{i.sheet or ''}:{i.cell or i.pointer or ''}: {i.message}" for i in self.issues))

def strict_json(text):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError("Duplicate JSON key: "+key)
            result[key]=value
        return result
    def reject(value):raise ValueError("Non-finite JSON number: "+value)
    return json.loads(text,object_pairs_hook=pairs,parse_float=Decimal,parse_constant=reject)

def read_input(path):
    path=Path(path)
    with path.open("rb") as stream:data=stream.read(MAX_BYTES+1)
    if not 0<len(data)<=MAX_BYTES:raise ImportFailure((ImportIssue(path.name,"File must be 1 byte..10 MiB"),))
    return data

def document(data,name,media_type):
    if type(data) is not bytes or not 0<len(data)<=MAX_BYTES:
        raise ImportFailure((ImportIssue(name,"Input must be 1 byte..10 MiB"),))
    return ImportDocument(document_id=name,document_hash=hashlib.sha256(data).hexdigest(),media_type=media_type,size_bytes=len(data))

@dataclass
class LocatedRow:
    values: dict
    document: ImportDocument
    pointer: str | None = None
    sheet: str | None = None
    row_number: int | None = None
    columns: dict | None = None
    locations: dict | None = None
    def issue(self,key,message):
        return ImportIssue(self.document.document_id,message,sheet=self.sheet,
            cell=(self.locations.get(key) if self.locations and key in self.locations else self.columns.get(key,"A")+str(self.row_number)) if self.sheet else None,
            pointer=(self.pointer+"/"+key) if self.pointer is not None else None)
    def read(self,key,converter):
        try:return converter(self.values.get(key))
        except ImportFailure:raise
        except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
            raise ImportFailure((self.issue(key,str(exc)),)) from exc
    def source(self,quote,key="quote"):
        location=self.issue(key,"")
        return SourceReference(document_id=self.document.document_id,document_hash=self.document.document_hash,
            quote=quote,sheet=self.sheet,cell=location.cell,json_pointer=location.pointer)

@dataclass(frozen=True)
class ImportBundle:
    document: ImportDocument
    old_table: DecisionTable
    old_rules: tuple[Rule,...]
    new_table: DecisionTable
    new_rules: tuple[Rule,...]
    existing_tests: tuple[TestCase,...]
    old_as_of: date | None = None
    new_as_of: date | None = None
