import hashlib,io,json,tempfile,unittest,importlib.util
from pathlib import Path
from contextlib import redirect_stdout,redirect_stderr
from unittest.mock import patch
from factory.parsers.templates import demo_payload,json_bytes,xlsx_bytes
from factory.parsers.json_parser import JsonParser
from factory.parsers.common import ImportFailure
from factory.repositories.connection import Database
from factory.repositories.document_repository import DocumentRepository
from factory.services.workflow_service import WorkflowService
from factory.services.import_service import ImportService
from factory.models import WorkflowStatus
from factory.exceptions import ValidationError,NotFoundError
from scripts.import_documents import main

EXCEL=importlib.util.find_spec("openpyxl") is not None and importlib.util.find_spec("defusedxml") is not None

class ImportWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="rule2test-import-");self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.path=self.root/"workflow.db";self.db=Database(self.path)
        self.workflow=WorkflowService(self.db);self.service=ImportService(self.workflow)
        self.file=self.root/"rules.json";self.data=json_bytes(demo_payload());self.file.write_bytes(self.data)
    def test_import_archive_restart_and_review(self):
        w=self.service.create(self.file,actor="BA")
        self.assertEqual(w.status,WorkflowStatus.DRAFT);self.assertEqual(w.approvals,())
        self.file.write_text("source edited after import",encoding="utf-8")
        service=ImportService(WorkflowService(Database(self.path)))
        doc,data=service.source(w.workflow_id,w.documents[0].document_hash)
        self.assertEqual(data,self.data);self.assertEqual(doc,w.documents[0])
        w=self.workflow.analyze(w.workflow_id,w.revision,actor="BA")
        w=self.workflow.start_review(w.workflow_id,w.revision,actor="QA")
        self.assertEqual(w.status,WorkflowStatus.IN_REVIEW);self.assertTrue(w.tests);self.assertEqual(w.approvals,())
        self.assertEqual(self.workflow.get(w.workflow_id).documents,(doc,))
    def test_invalid_input_creates_no_workflow(self):
        p=demo_payload();p["rules_v2"][1]["value"]=200;self.file.write_bytes(json_bytes(p))
        with self.assertRaises(ImportFailure):self.service.create(self.file,actor="BA")
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM wf_heads").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM wf_source_documents").fetchone()[0],0)
    def test_archive_failure_rolls_back_snapshots_and_head(self):
        with patch.object(DocumentRepository,"put",side_effect=RuntimeError("injected archive failure")):
            with self.assertRaises(RuntimeError):self.service.create(self.file,actor="BA")
        with self.db.read() as c:
            for table in ("wf_heads","wf_objects","wf_events","wf_source_documents"):
                self.assertEqual(c.execute("SELECT count(*) FROM "+table).fetchone()[0],0)
    def test_corrupt_archive_is_detected(self):
        w=self.service.create(self.file,actor="BA")
        with self.db.transaction() as c:c.execute("UPDATE wf_source_documents SET data=?",(b"corrupt",))
        with self.assertRaises(ValidationError):self.service.source(w.workflow_id,w.documents[0].document_hash)
    def test_sources_are_scoped_to_workflow(self):
        one=self.service.create(self.file,actor="BA")
        p=demo_payload("claim_review");self.file.write_bytes(json_bytes(p))
        two=self.service.create(self.file,actor="BA")
        with self.assertRaises(NotFoundError):self.service.source(two.workflow_id,one.documents[0].document_hash)
    def test_create_rejects_wrong_raw_bytes_before_commit(self):
        b=JsonParser().parse(self.data,"rules.json")
        with self.assertRaises(ValidationError):self.workflow.create(b.old_table,b.old_rules,b.new_table,b.new_rules,b.existing_tests,
            actor="BA",source_documents=((b.document,b"wrong"),))
        with self.db.read() as c:self.assertEqual(c.execute("SELECT count(*) FROM wf_heads").fetchone()[0],0)
    def test_migration_from_v1_retains_old_snapshot_hashes(self):
        from tests.fixtures.engine_cases import scenario
        table,rules=scenario("eligibility")
        w=self.workflow.create(table,rules,table,rules,actor="BA")
        with self.db.transaction() as c:
            before=c.execute("SELECT hash FROM wf_objects WHERE kind='workflow'").fetchone()[0]
            c.execute("DROP TABLE wf_source_documents");c.execute("DELETE FROM wf_schema_migrations WHERE version=2")
        restored=WorkflowService(Database(self.path)).get(w.workflow_id)
        self.assertEqual(restored,w);self.assertNotIn("documents",restored.to_dict())
        with self.db.read() as c:
            self.assertEqual(c.execute("SELECT hash FROM wf_objects WHERE kind='workflow'").fetchone()[0],before)
            self.assertEqual(c.execute("SELECT count(*) FROM wf_schema_migrations").fetchone()[0],2)
    def call(self,args,code=0):
        out=io.StringIO();err=io.StringIO()
        with redirect_stdout(out),redirect_stderr(err):actual=main(args)
        self.assertEqual(actual,code,err.getvalue())
        return json.loads(out.getvalue() if code==0 else err.getvalue())
    def test_cli_validate_no_database_and_export_without_overwrite(self):
        db=self.root/"not-created.db"
        result=self.call(["--db",str(db),"validate",str(self.file)])
        self.assertTrue(result["valid"]);self.assertFalse(db.exists())
        w=self.call(["--db",str(self.path),"create",str(self.file),"--actor","BA"])
        output=self.root/"recovered.json"
        args=["--db",str(self.path),"source","--workflow",w["workflow_id"],"--hash",w["documents"][0]["document_hash"],"--output",str(output)]
        self.call(args);self.assertEqual(output.read_bytes(),self.data)
        self.call(args,2);self.assertEqual(output.read_bytes(),self.data)
    def test_cli_invalid_create_does_not_initialize_database(self):
        db=self.root/"not-created.db";self.file.write_text("invalid",encoding="utf-8")
        result=self.call(["--db",str(db),"create",str(self.file),"--actor","BA"],2)
        self.assertFalse(result["valid"]);self.assertFalse(db.exists())
    @unittest.skipUnless(EXCEL,"Install requirements-excel.txt")
    def test_excel_to_review(self):
        self.file=self.root/"policy.xlsx";self.file.write_bytes(xlsx_bytes(demo_payload("deductible")))
        w=self.service.create(self.file,actor="BA")
        w=self.workflow.analyze(w.workflow_id,w.revision,actor="BA")
        w=self.workflow.start_review(w.workflow_id,w.revision,actor="QA")
        self.assertEqual(w.status,WorkflowStatus.IN_REVIEW)
        self.assertEqual(w.new_rules[0].sources[0].cell,"N2")
        self.assertEqual(self.service.source(w.workflow_id,w.documents[0].document_hash)[1],self.file.read_bytes())
    @unittest.skipUnless(EXCEL,"Install requirements-excel.txt")
    def test_seed_preserves_existing_and_reset_only_known_fixtures(self):
        from scripts.seed_demo import seed
        directory=self.root/"demo";seed(directory)
        custom=directory/"notes.txt";custom.write_text("keep")
        db=directory/"workflow.db";db.write_bytes(b"keep database")
        existing=directory/"eligibility.json";existing.write_text("edited")
        self.assertEqual(seed(directory),[]);self.assertEqual(existing.read_text(),"edited")
        self.assertEqual(len(seed(directory,overwrite=True)),6)
        self.assertEqual(custom.read_text(),"keep");self.assertEqual(db.read_bytes(),b"keep database")
        self.assertEqual(JsonParser().parse_path(existing).new_rules[0].version,2)
