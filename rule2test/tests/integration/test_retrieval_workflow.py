import tempfile,unittest,json,io
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch,Mock
from contextlib import redirect_stdout,redirect_stderr
from factory.models import content_hash,ApprovalDecision,WorkflowStatus,Outcome
from factory.repositories.connection import Database
from factory.repositories.document_repository import DocumentRepository
from factory.services.knowledge_service import KnowledgeService
from factory.services.retrieval_generation_service import RetrievalGenerationService
from factory.services.workflow_service import WorkflowService
from factory.services.approval_service import ApprovalService
from factory.services.import_service import ImportService
from factory.providers.embedding.mock import MockEmbeddingProvider
from factory.providers.llm.test_suggestions import MockTestSuggestionProvider,OllamaTestSuggestionProvider
from factory.exceptions import ValidationError,ConflictError,ProviderError
from scripts.run_retrieval_demo import reviewed_source,target_workflow,evaluate

class RetrievalWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="rule2test-retrieval-");self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.path=self.root/"demo.db";self.db=Database(self.path)
        self.source=reviewed_source(self.db,"eligibility")
        self.knowledge=KnowledgeService(self.db)
        self.index=self.knowledge.build((self.source.workflow_id,),actor="Curator")
        self.target=target_workflow(self.db,self.source)
        self.service=RetrievalGenerationService(self.db,MockTestSuggestionProvider(),self.knowledge)
    def propose(self):
        return self.service.propose(self.target.workflow_id,self.target.revision,self.index.index_id,"age eligibility",actor="BA")
    def revoke(self):
        a=self.source.approvals[0]
        self.source=ApprovalService(self.db).review(self.source.workflow_id,self.source.revision,test_id=a.subject_id,test_revision=a.revision,
            decision=ApprovalDecision.REJECTED,reviewer="QA",reason="Revoke for regression test")
    def test_only_approved_rule_and_test_snapshots_are_indexed(self):
        self.assertEqual(len(self.index.records),2)
        self.assertEqual({r.kind for r in self.index.records},{"rule","test"})
        self.assertEqual(KnowledgeService(Database(self.path)).get(self.index.index_id),self.index)
        test=next(r.test for r in self.index.records if r.test)
        self.assertEqual(test.expected.outcome,Outcome.DENY)
        self.assertGreater(len(self.source.tests),1)
    def test_rejected_test_is_removed_from_search_without_rebuild(self):
        self.revoke()
        self.assertFalse(self.knowledge.search(self.index.index_id,"age",kind="test"))
        self.assertTrue(self.knowledge.search(self.index.index_id,"age",kind="rule"))
    def test_edited_test_revision_cannot_reuse_old_index_approval(self):
        a=self.source.approvals[0];test=next(t for t in self.source.tests if t.test_id==a.subject_id)
        WorkflowService(self.db).edit_test(self.source.workflow_id,self.source.revision,test_id=test.test_id,test_revision=test.revision,
            inputs=test.inputs,expected=test.expected,actor="QA",reason="New test revision")
        self.assertFalse(self.knowledge.search(self.index.index_id,"age",kind="test"))
    def test_rule_revision_invalidates_rule_knowledge(self):
        from factory.models import RuleReference
        rule=replace(self.source.new_rules[0],version=3)
        ref=RuleReference(rule_id=rule.rule_id,version=3,rule_hash=content_hash(rule))
        table=replace(self.source.new_table,version=3,rows=(replace(self.source.new_table.rows[0],rule=ref),))
        WorkflowService(self.db).revise_rules(self.source.workflow_id,self.source.revision,table=table,rules=(rule,),actor="BA",reason="New rule revision")
        self.assertFalse(self.knowledge.search(self.index.index_id,"age"))
    def test_tied_scores_are_ranked_by_record_content_not_by_generated_identifier(self):
        # Record identifiers derive from a per-run workflow UUID, so ranking on them made the
        # reported rank of a tied record differ between runs over identical content, which in turn
        # made the published retrieval figure irreproducible. An English query over the Japanese
        # corpus scores every record alike, so the ordering is decided entirely by the tie-break.
        def ordered(name):
            database=Database(self.root/(name+".db"))
            sources=[reviewed_source(database,profile) for profile in ("eligibility","claim_review","deductible")]
            knowledge=KnowledgeService(database)
            index=knowledge.build(tuple(s.workflow_id for s in sources),actor="Curator")
            return knowledge.search(index.index_id,"When should a claim be reviewed manually?",kind="test",top_k=3)
        orders=[]
        for attempt in range(5):
            hits=ordered("corpus-"+str(attempt))
            self.assertEqual(len(hits),3)
            self.assertEqual(len({round(h.score,9) for h in hits}),1,"expected a full tie to exercise the tie-break")
            keys=[(-round(h.score,9),h.record.kind,h.record.text) for h in hits]
            # Ranking a tie on a random identifier would order these independently of content.
            self.assertEqual(keys,sorted(keys))
            orders.append(keys)
        self.assertEqual(len({tuple(order) for order in orders}),1)

    def test_fields_within_keeps_only_records_the_target_policy_can_express(self):
        # search(fields=...) keeps records covering every named field; fields_within is the
        # opposite direction and is what candidate generation needs.
        covering=self.knowledge.search(self.index.index_id,"age eligibility",fields=("age",),top_k=5)
        self.assertTrue(covering)
        self.assertEqual(self.knowledge.search(self.index.index_id,"age eligibility",fields_within=(),top_k=5),())
        within=self.knowledge.search(self.index.index_id,"age eligibility",fields_within=("age",),top_k=5)
        self.assertTrue(all(set(h.record.fields)<={"age"} for h in within))
        with self.assertRaises(ValidationError):
            self.knowledge.search(self.index.index_id,"age eligibility",fields_within=("premium",))

    def test_field_workflow_kind_and_exclusion_filters(self):
        self.assertFalse(self.knowledge.search(self.index.index_id,"age",fields=("claim_amount",)))
        self.assertFalse(self.knowledge.search(self.index.index_id,"age",workflow_ids=(self.target.workflow_id,)))
        self.assertFalse(self.knowledge.search(self.index.index_id,"age",exclude_workflow=self.source.workflow_id))
        hits=self.knowledge.search(self.index.index_id,"age",kind="test",rule_ids=("R-eligibility",),top_k=1)
        self.assertEqual(len(hits),1);self.assertTrue(hits[0].rule_id_match)
    def test_embedding_identity_mismatch_and_bad_vectors_fail(self):
        other=MockEmbeddingProvider();other.identity="different"
        with self.assertRaises(ValidationError):KnowledgeService(self.db,embedding=other).search(self.index.index_id,"age")
        class Bad(MockEmbeddingProvider):
            def embed(self,texts):return tuple((float("nan"),)*128 for _ in texts)
        with self.assertRaises(ValidationError):KnowledgeService(self.db,embedding=Bad()).build((self.source.workflow_id,),actor="BA")
    def test_corrupt_index_detected(self):
        with self.db.transaction() as c:c.execute("UPDATE wf_objects SET hash=? WHERE kind='knowledge_index'",("0"*64,))
        with self.assertRaises(ValidationError):self.knowledge.search(self.index.index_id,"age")
    def test_expected_recomputed_deduplicated_and_gap_claim_is_honest(self):
        batch=self.propose()
        self.assertTrue(batch.simulated);self.assertEqual(len(batch.candidates),1);self.assertGreater(batch.duplicate_count,0)
        test=batch.candidates[0];self.assertEqual(test.inputs[0].value.data,66)
        self.assertEqual(test.expected.outcome,Outcome.ALLOW)
        self.assertEqual(test.obligation_ids,())  # An extra regression example, not a newly closed boundary gap.
        self.assertEqual(WorkflowService(self.db).get(self.target.workflow_id),self.target)
    def test_attach_archives_context_and_requires_test_review(self):
        batch=self.propose();w=self.service.attach(batch.batch_id,content_hash(batch),actor="BA")
        self.assertEqual(w.status,WorkflowStatus.IN_REVIEW);self.assertEqual(w.approvals,())
        self.assertEqual(len(w.tests),len(self.target.tests)+1)
        doc,raw=ImportService(WorkflowService(self.db)).source(w.workflow_id,content_hash(self.index))
        self.assertEqual(raw,self.index.to_json().encode())
        pointer=batch.candidates[0].sources[0].json_pointer.split("/")
        self.assertEqual(json.loads(raw)["records"][int(pointer[2])]["text"],batch.candidates[0].sources[0].quote)
        with self.assertRaises(ConflictError):ApprovalService(self.db).finalize(w.workflow_id,w.revision,reviewer="QA",reason="No approvals")
        with self.assertRaises(ConflictError):self.service.attach(batch.batch_id,content_hash(batch),actor="BA")
    def test_batch_hash_and_stale_target_block_attach(self):
        batch=self.propose()
        with self.assertRaises(ConflictError):self.service.attach(batch.batch_id,"0"*64,actor="BA")
        test=self.target.tests[0]
        WorkflowService(self.db).edit_test(self.target.workflow_id,self.target.revision,test_id=test.test_id,test_revision=test.revision,
            inputs=test.inputs,expected=test.expected,actor="QA",reason="Concurrent edit")
        with self.assertRaises(ConflictError):self.service.attach(batch.batch_id,content_hash(batch),actor="BA")
    def test_revoked_reference_blocks_existing_batch(self):
        batch=self.propose();self.revoke()
        with self.assertRaises(ValidationError):self.service.attach(batch.batch_id,content_hash(batch),actor="BA")
    def test_source_changes_during_provider_call_are_detected(self):
        outer=self
        class Concurrent(MockTestSuggestionProvider):
            def suggest(self,w,hits,**kwargs):
                result=super().suggest(w,hits,**kwargs);outer.revoke();return result
        self.service.provider=Concurrent()
        with self.assertRaises(ValidationError):self.propose()
        with self.db.read() as c:self.assertEqual(c.execute("SELECT count(*) FROM wf_objects WHERE kind='retrieval_batch'").fetchone()[0],0)
    def test_invalid_output_reference_expected_and_duplicate_json_rejected(self):
        hits=self.knowledge.search(self.index.index_id,"age",kind="test")
        ref=hits[0].record.record_id;inputs=[x.to_dict() for x in hits[0].record.test.inputs]
        for row in (dict(inputs=inputs,reference_ids=["invented"],reason="bad"),
            dict(inputs=inputs,reference_ids=[ref],reason="bad",expected="deny")):
            class Invalid(MockTestSuggestionProvider):
                def suggest(self,*args,**kwargs):return json.dumps(dict(candidates=[row]))
            self.service.provider=Invalid()
            with self.assertRaises(ValidationError):self.propose()
        class Duplicate(MockTestSuggestionProvider):
            def suggest(self,*args,**kwargs):return '{"candidates":[],"candidates":[]}'
        self.service.provider=Duplicate()
        with self.assertRaises(ValueError):self.propose()
    def test_provider_error_does_not_change_workflow(self):
        self.service.provider=Mock();self.service.provider.suggest.side_effect=RuntimeError("secret")
        with self.assertRaises(ProviderError) as ctx:self.propose()
        self.assertNotIn("secret",str(ctx.exception))
        self.assertEqual(WorkflowService(self.db).get(self.target.workflow_id),self.target)
    def test_archive_failure_rolls_back_attachment(self):
        batch=self.propose()
        with patch.object(DocumentRepository,"put",side_effect=RuntimeError("disk")):
            with self.assertRaises(RuntimeError):self.service.attach(batch.batch_id,content_hash(batch),actor="BA")
        self.assertEqual(WorkflowService(self.db).get(self.target.workflow_id),self.target)
    def test_no_hits_does_not_call_provider_or_invent_candidates(self):
        empty=self.knowledge.build((self.target.workflow_id,),actor="BA")
        self.service.provider=Mock();self.service.provider.name="spy";self.service.provider.simulated=True
        batch=self.service.propose(self.target.workflow_id,self.target.revision,empty.index_id,"age",actor="BA")
        self.service.provider.suggest.assert_not_called();self.assertEqual(batch.candidates,())
    def test_cli_show_and_attach(self):
        from scripts.retrieval_cli import main
        batch=self.propose()
        def call(args):
            out=io.StringIO();err=io.StringIO()
            with redirect_stdout(out),redirect_stderr(err):code=main(["--db",str(self.path)]+args)
            self.assertEqual(code,0,err.getvalue());return json.loads(out.getvalue())
        self.assertEqual(call(["show","--batch",batch.batch_id])["batch_hash"],content_hash(batch))
        w=call(["attach","--batch",batch.batch_id,"--hash",content_hash(batch),"--actor","BA"])
        self.assertEqual(w["status"],"in_review")
    def test_synthetic_retrieval_ground_truth(self):
        sources={"eligibility":self.source,"claim_review":reviewed_source(self.db,"claim_review"),"deductible":reviewed_source(self.db,"deductible")}
        index=self.knowledge.build(tuple(w.workflow_id for w in sources.values()),actor="BA")
        report=evaluate(self.knowledge,index,sources)
        self.assertEqual(report["recall_at_3"],1.0);self.assertEqual(report["mrr_at_3"],1.0);self.assertTrue(report["simulated"])
    def test_ollama_suggestion_prompt_forbids_expected_output(self):
        provider=OllamaTestSuggestionProvider("test-model")
        hits=self.knowledge.search(self.index.index_id,"age")
        with patch.object(provider.client,"complete",return_value='{"candidates":[]}') as complete:
            self.assertEqual(provider.suggest(self.target,hits,timeout_seconds=9),'{"candidates":[]}')
            payload=json.loads(complete.call_args.kwargs["user_message"])
            self.assertTrue(payload["references"]);self.assertNotIn("expected",payload["references"][0])
            self.assertIn("Do not return expected",complete.call_args.kwargs["system_prompt"])
