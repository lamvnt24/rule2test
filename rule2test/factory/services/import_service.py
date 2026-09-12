"""Validate once, then atomically archive the source and create a DRAFT workflow."""
from pathlib import Path
from factory.parsers.common import read_input,ImportFailure,ImportIssue
from factory.parsers.json_parser import JsonParser
from factory.parsers.excel_parser import ExcelParser
from factory.repositories.document_repository import DocumentRepository

class ImportService:
    def __init__(self,workflow_service=None):
        self.workflow_service=workflow_service

    @staticmethod
    def parse(data,name,header_mapping=None):
        extension=Path(name).suffix.lower()
        if extension==".json":
            if header_mapping:raise ImportFailure((ImportIssue(name,"Header mapping applies only to XLSX"),))
            return JsonParser().parse(data,name)
        if extension==".xlsx":return ExcelParser(header_mapping).parse(data,name)
        raise ImportFailure((ImportIssue(name,"Supported formats: .json, .xlsx"),))

    def validate(self,path,header_mapping=None):
        path=Path(path)
        return self.parse(read_input(path),path.name,header_mapping)

    def create(self,path,*,actor,header_mapping=None):
        path=Path(path)
        data=read_input(path)
        bundle=self.parse(data,path.name,header_mapping)
        if self.workflow_service is None:raise ValueError("Workflow service is required for persistence")
        return self.workflow_service.create(bundle.old_table,bundle.old_rules,bundle.new_table,bundle.new_rules,
            bundle.existing_tests,actor=actor,old_as_of=bundle.old_as_of,new_as_of=bundle.new_as_of,
            source_documents=((bundle.document,data),))

    def source(self,workflow_id,document_hash):
        if self.workflow_service is None:raise ValueError("Workflow service is required")
        with self.workflow_service.db.read() as c:
            workflow=self.workflow_service.workflows.current(c,workflow_id)
            document,data=DocumentRepository().get(c,workflow_id,document_hash)
            if document not in workflow.documents:raise ValueError("Document is not in current workflow manifest")
            return document,data
