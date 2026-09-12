"""Strict immutable domain contracts and lossless JSON serialization."""
from __future__ import annotations
import json, re, types
from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Union, get_args, get_origin, get_type_hints
from factory.exceptions import ValidationError

def require(condition, message):
    if not condition:
        raise ValidationError(message)

def nonempty(value, name):
    require(isinstance(value, str) and bool(value.strip()), name + " must be non-empty")

def sha256(value, name="hash"):
    require(isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None, name + " must be lowercase SHA-256")

def aware(value):
    require(value.tzinfo is not None and value.utcoffset() is not None, "timestamp must include timezone")

def _check(value, annotation):
    origin=get_origin(annotation)
    if origin in (Union, types.UnionType):
        return any(_check(value, a) for a in get_args(annotation))
    if origin is tuple:
        args=get_args(annotation)
        return type(value) is tuple and all(_check(v,args[0]) for v in value)
    if annotation is type(None): return value is None
    return type(value) is annotation

def _encode(value):
    if isinstance(value, Model): return value.to_dict()
    if isinstance(value, Enum): return value.value
    if isinstance(value, Decimal): return {"$decimal":str(value)}
    if isinstance(value, datetime): return {"$datetime":value.isoformat()}
    if isinstance(value, date): return {"$date":value.isoformat()}
    if isinstance(value, tuple): return [_encode(v) for v in value]
    return value

def _decode(value, annotation):
    origin=get_origin(annotation)
    if origin in (Union, types.UnionType):
        for choice in get_args(annotation):
            try:
                candidate=_decode(value,choice)
                if _check(candidate,choice): return candidate
            except (ValidationError, ValueError, TypeError, KeyError): pass
        raise ValidationError("Value does not match any supported type")
    if origin is tuple:
        require(type(value) is list, "Expected JSON array")
        return tuple(_decode(v,get_args(annotation)[0]) for v in value)
    if isinstance(annotation,type) and issubclass(annotation,Model):
        return annotation.from_dict(value)
    if isinstance(annotation,type) and issubclass(annotation,Enum):
        return annotation(value)
    if annotation in (Decimal,date,datetime):
        tag={Decimal:"$decimal",date:"$date",datetime:"$datetime"}[annotation]
        require(type(value) is dict and set(value)=={tag}, "Expected tagged "+annotation.__name__)
        require(type(value[tag]) is str,"Tagged value must be a string")
        if annotation is Decimal:
            try: return Decimal(value[tag])
            except InvalidOperation as exc: raise ValidationError("Invalid decimal value") from exc
        return annotation.fromisoformat(value[tag])
    require(_check(value,annotation), "Incorrect JSON value type")
    return value

def _json_object(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,"Duplicate JSON key: "+key)
        result[key]=value
    return result

@dataclass(frozen=True, kw_only=True)
class Model:
    def __post_init__(self):
        for name,annotation in get_type_hints(type(self)).items():
            require(_check(getattr(self,name),annotation), type(self).__name__+"."+name+": incorrect type")
    def to_dict(self):
        return {f.name:_encode(getattr(self,f.name)) for f in fields(self)}
    def to_json(self):
        return json.dumps(self.to_dict(),ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
    @classmethod
    def from_dict(cls, value):
        require(type(value) is dict,"Expected object")
        hints=get_type_hints(cls)
        require(not set(value)-set(hints),"Unknown fields: "+str(set(value)-set(hints)))
        try:
            return cls(**{k:_decode(v,hints[k]) for k,v in value.items()})
        except (ValueError,TypeError,KeyError) as exc:
            raise ValidationError(str(exc)) from exc
    @classmethod
    def from_json(cls,text):
        try: return cls.from_dict(json.loads(text,object_pairs_hook=_json_object))
        except (ValueError,TypeError) as exc: raise ValidationError(str(exc)) from exc

class ValueKind(str,Enum):
    INTEGER="integer"
    MONEY="money"
    DATE="date"
    TEXT="text"
    BOOLEAN="boolean"
    NULL="null"
    MISSING="missing"

@dataclass(frozen=True,kw_only=True)
class Value(Model):
    kind: ValueKind
    data: int | Decimal | date | str | bool | None = None
    currency: str | None = None
    def __post_init__(self):
        super().__post_init__()
        expected={ValueKind.INTEGER:int,ValueKind.MONEY:Decimal,ValueKind.DATE:date,
                  ValueKind.TEXT:str,ValueKind.BOOLEAN:bool,ValueKind.NULL:type(None),ValueKind.MISSING:type(None)}
        require(type(self.data) is expected[self.kind],"Value data does not match kind")
        if self.kind is ValueKind.MONEY:
            require(self.data.is_finite(),"Money must be finite")
            require(self.currency is not None and re.fullmatch(r"[A-Z]{3}",self.currency) is not None,"Money requires a three-letter currency code")
        else: require(self.currency is None,"Currency only applies to money")

@dataclass(frozen=True,kw_only=True)
class SourceReference(Model):
    document_id: str
    document_hash: str
    quote: str
    sheet: str | None = None
    cell: str | None = None
    page: int | None = None
    json_pointer: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    def to_dict(self):
        result=super().to_dict()
        if self.json_pointer is None:result.pop("json_pointer")
        if self.line_start is None:result.pop("line_start")
        if self.line_end is None:result.pop("line_end")
        return result
    def __post_init__(self):
        super().__post_init__()
        nonempty(self.document_id,"document_id");sha256(self.document_hash,"document_hash");nonempty(self.quote,"quote")
        require((self.sheet is None)==(self.cell is None),"Excel source requires both sheet and cell")
        if self.sheet is not None:
            nonempty(self.sheet,"sheet")
            require(re.fullmatch(r"[A-Z]+[1-9][0-9]*(?::[A-Z]+[1-9][0-9]*)?",self.cell) is not None,"Invalid Excel cell/range")
        require((self.line_start is None)==(self.line_end is None),"Text source requires start and end lines")
        if self.line_start is not None:
            require(1<=self.line_start<=self.line_end,"Invalid source line interval")
            require(self.sheet is None and self.page is None and self.json_pointer is None,"Text line source cannot mix locators")
        if self.page is not None: require(self.page>0,"Page is one-based")
        if self.json_pointer is not None:
            require(self.json_pointer=="" or self.json_pointer.startswith("/"),"Invalid JSON Pointer")
            require(re.search(r"~(?![01])",self.json_pointer) is None,"Invalid JSON Pointer escape")
            require(self.sheet is None and self.page is None,"JSON source cannot also use sheet/page")

@dataclass(frozen=True,kw_only=True)
class RuleReference(Model):
    rule_id: str
    version: int
    rule_hash: str
    def __post_init__(self):
        super().__post_init__();nonempty(self.rule_id,"rule_id")
        require(self.version>0,"Version must be positive");sha256(self.rule_hash,"rule_hash")

@dataclass(frozen=True,kw_only=True)
class Metadata(Model):
    created_at: datetime
    created_by: str
    schema_version: int = 1
    def __post_init__(self):
        super().__post_init__();aware(self.created_at);nonempty(self.created_by,"created_by")
        require(self.schema_version==1,"Unsupported schema version")

class WorkflowStatus(str,Enum):
    DRAFT="draft"
    ANALYZED="analyzed"
    IN_REVIEW="in_review"
    APPROVED="approved"
    EXECUTING="executing"
    INTERRUPTED="interrupted"
    EXECUTED="executed"
    EVIDENCED="evidenced"