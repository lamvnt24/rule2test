"""Strict version-1 JSON table import with JSON Pointer provenance."""
from .common import LocatedRow,ImportFailure,ImportIssue,strict_json,document,read_input,MAX_ROWS
from .schema import MANIFEST_KEYS,SHEETS,JSON_KEYS
from ._builder import compile_document
from pathlib import Path

class JsonParser:
    def parse_path(self,path):
        return self.parse(read_input(path),Path(path).name)

    def parse(self,data,name="import.json"):
        doc=document(data,name,"application/json")
        try:payload=strict_json(data.decode("utf-8-sig"))
        except (ValueError,UnicodeError,RecursionError) as exc:
            raise ImportFailure((ImportIssue(name,"Invalid UTF-8 JSON: "+str(exc),pointer=""),)) from exc
        if type(payload) is not dict:raise ImportFailure((ImportIssue(name,"Expected a JSON object",pointer=""),))
        issues=[]
        expected=set(MANIFEST_KEYS)|set(JSON_KEYS)
        for key in sorted(expected-set(payload)):issues.append(ImportIssue(name,"Missing field",pointer="/"+key))
        for key in sorted(set(payload)-expected):issues.append(ImportIssue(name,"Unknown field",pointer="/"+key))
        tables={}
        for key,sheet in JSON_KEYS.items():
            rows=payload.get(key)
            if type(rows) is not list or len(rows)>MAX_ROWS:
                issues.append(ImportIssue(name,"Expected an array with at most 5000 rows",pointer="/"+key));continue
            located=[]
            for i,row in enumerate(rows):
                pointer=f"/{key}/{i}"
                if type(row) is not dict:
                    issues.append(ImportIssue(name,"Expected row object",pointer=pointer));continue
                columns=set(SHEETS[sheet])
                for missing in sorted(columns-set(row)):issues.append(ImportIssue(name,"Missing column",pointer=pointer+"/"+missing))
                for extra in sorted(set(row)-columns):issues.append(ImportIssue(name,"Unknown column",pointer=pointer+"/"+extra))
                located.append(LocatedRow(row,doc,pointer=pointer))
            tables[sheet]=located
        if issues:raise ImportFailure(issues[:100])
        try:return compile_document(doc,LocatedRow({k:payload[k] for k in MANIFEST_KEYS},doc,pointer=""),tables)
        except ImportFailure:raise
        except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
            raise ImportFailure((ImportIssue(name,str(exc),pointer=""),)) from exc
