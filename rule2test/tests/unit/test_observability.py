"""Phase 11 contracts: log redaction, trace propagation, bounded metrics and classified provider failures."""
import io,json,socket,unittest,urllib.error
from factory.observability import logger,metrics,tracing
from factory.exceptions import ConfigurationError,ProviderError,ValidationError
from factory.providers.failure import classify,failure,REMEDIATION
from factory.server import route_label

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.buffer=io.StringIO();metrics.reset()
        self.previous=dict(logger._STATE)
        logger._STATE.update(level=logger.LEVELS["debug"],level_name="debug",stream=self.buffer,destination="memory",owned=False)
        self.addCleanup(lambda:logger._STATE.update(self.previous))
        self.addCleanup(metrics.reset)
    def records(self):
        return [json.loads(line) for line in self.buffer.getvalue().strip().splitlines() if line]

class LoggingContractTests(CaptureTests):
    def test_unknown_fields_are_dropped_and_only_counted(self):
        logger.info("extraction",workflow_id="wf-1",source_text="加入年齢は18歳",reviewer="Alice",prompt="system prompt")
        record=self.records()[0]
        self.assertEqual(record["workflow_id"],"wf-1")
        self.assertEqual(record["dropped_fields"],3)
        self.assertNotIn("source_text",record);self.assertNotIn("reviewer",record);self.assertNotIn("prompt",record)
        self.assertNotIn("Alice",self.buffer.getvalue())

    def test_unsupported_value_types_are_dropped(self):
        logger.info("event",count=[1,2],total=object(),revision=4,duration_ms=float("nan"))
        record=self.records()[0]
        self.assertEqual(record["revision"],4);self.assertEqual(record["dropped_fields"],3)

    def test_long_strings_are_truncated(self):
        logger.info("event",model="m"*500)
        self.assertEqual(len(self.records()[0]["model"]),logger.MAX_TEXT)

    def test_level_filters_lower_severity(self):
        logger._STATE.update(level=logger.LEVELS["warn"],level_name="warn")
        logger.info("ignored");logger.error("kept")
        self.assertEqual([r["event"] for r in self.records()],["kept"])

    def test_records_are_single_line_json(self):
        logger.info("multi\nline",model="a\nb")
        self.assertEqual(len(self.buffer.getvalue().strip().splitlines()),1)

    def test_configure_rejects_an_unknown_level(self):
        with self.assertRaises(ConfigurationError):logger.configure(dict(RULE2TEST_LOG_LEVEL="verbose"))

    def test_configure_off_disables_output(self):
        result=logger.configure(dict(RULE2TEST_LOG_LEVEL="off"))
        self.assertEqual(result["destination"],"none")
        logger.info("dropped")
        self.assertEqual(self.records(),[])

    def test_importing_the_library_does_not_start_logging(self):
        logger._STATE.update(level=logger.LEVELS["off"],stream=None,destination="none")
        logger.error("nothing")
        self.assertEqual(self.buffer.getvalue(),"")

class TracingContractTests(CaptureTests):
    def test_one_trace_id_covers_every_nested_span(self):
        with tracing.trace("http_request",component="transport"):
            with tracing.span("analyze",component="service"):
                with tracing.span("oracle",component="engine"):pass
        traces={record["trace_id"] for record in self.records()}
        self.assertEqual(len(traces),1)
        self.assertEqual([r["span"] for r in self.records()],["oracle","analyze","http_request"])
        self.assertEqual([r["depth"] for r in self.records()],[2,1,0])

    def test_separate_traces_get_separate_identities(self):
        for _ in range(2):
            with tracing.trace("run",component="cli"):pass
        self.assertEqual(len({r["trace_id"] for r in self.records()}),2)

    def test_trace_id_is_cleared_after_the_block(self):
        with tracing.trace("run",component="cli"):self.assertTrue(logger.trace_id())
        self.assertEqual(logger.trace_id(),"")

    def test_span_records_the_error_class_but_never_the_message(self):
        with self.assertRaises(ProviderError):
            with tracing.span("ollama_chat",component="provider"):
                raise failure("timeout","secret host detail 10.0.0.7")
        record=self.records()[0]
        self.assertEqual(record["outcome"],"error")
        self.assertEqual(record["error_type"],"ProviderError")
        self.assertEqual(record["error_kind"],"timeout")
        self.assertNotIn("10.0.0.7",self.buffer.getvalue())

    def test_span_depth_is_bounded(self):
        def nest(remaining):
            if not remaining:return tracing.depth()
            with tracing.span("deep",component="test"):return nest(remaining-1)
        with tracing.trace("run",component="cli"):deepest=nest(40)
        self.assertLessEqual(deepest,tracing.MAX_DEPTH)

class MetricsContractTests(CaptureTests):
    def test_only_allowlisted_labels_become_dimensions(self):
        metrics.increment("calls_total",workflow_id="wf-1",actor="Alice",component="service")
        counter=metrics.snapshot()["counters"][0]
        self.assertEqual(counter["labels"],dict(component="service"))

    def test_unsafe_label_values_are_replaced(self):
        metrics.increment("calls_total",operation="a b\nc")
        self.assertEqual(metrics.snapshot()["counters"][0]["labels"],dict(operation="invalid"))

    def test_series_are_capped_and_the_drop_is_reported(self):
        for index in range(metrics.MAX_SERIES+25):metrics.increment("calls_total",operation="op-"+str(index))
        snapshot=metrics.snapshot()
        self.assertLessEqual(snapshot["series"],metrics.MAX_SERIES)
        self.assertGreater(snapshot["dropped_series"],0)

    def test_durations_report_bucket_bounded_quantiles(self):
        for value in (2,2,2,2,900):metrics.observe("span_duration_ms",value,operation="analyze")
        row=metrics.snapshot()["durations"][0]
        self.assertEqual(row["count"],5);self.assertEqual(row["max_ms"],900.0)
        self.assertEqual(row["p50_ms_upper_bound"],5)
        self.assertEqual(sum(row["buckets"].values()),5)

    def test_negative_and_non_finite_observations_are_ignored(self):
        metrics.observe("span_duration_ms",-1,operation="analyze")
        metrics.observe("span_duration_ms",float("inf"),operation="analyze")
        self.assertEqual(metrics.snapshot()["durations"],[])

    def test_snapshot_states_that_values_reset_on_restart(self):
        self.assertIn("reset on restart",metrics.snapshot()["scope"])

class ProviderFailureTests(unittest.TestCase):
    def test_every_kind_has_a_remediation_hint(self):
        self.assertEqual(set(ProviderError.KINDS),set(REMEDIATION))

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):ProviderError("boom",kind="made_up")

    def test_plain_construction_stays_supported(self):
        self.assertEqual(ProviderError("boom").kind,"unclassified")

    def test_payload_states_no_retry_and_no_fallback(self):
        payload=failure("timeout","Provider timed out").to_dict()
        self.assertFalse(payload["retried"]);self.assertFalse(payload["fallback_used"])
        self.assertEqual(payload["kind"],"timeout")

    def test_transport_exceptions_map_to_distinct_kinds(self):
        cases=((urllib.error.HTTPError("http://x",404,"missing",{},None),"model_mismatch"),
               (urllib.error.HTTPError("http://x",500,"boom",{},None),"http_status"),
               (socket.timeout(),"timeout"),
               (urllib.error.URLError(ConnectionRefusedError()),"unreachable"),
               (urllib.error.URLError(socket.timeout()),"timeout"),
               (ValidationError("dimension mismatch"),"schema_rejected"),
               (ValueError("not json"),"malformed_json"),
               (OSError("broken"),"unreachable"))
        for exception,kind in cases:
            with self.subTest(kind=kind):
                self.assertEqual(classify(exception,"Request failed").kind,kind)

    def test_an_already_classified_failure_is_not_reclassified(self):
        original=failure("model_mismatch","Wrong tag")
        self.assertIs(classify(original,"Request failed"),original)

    def test_classified_message_excludes_the_provider_payload(self):
        error=classify(urllib.error.HTTPError("http://127.0.0.1:11434/api/chat",500,"internal",{},None),"Ollama request failed")
        self.assertNotIn("11434",str(error));self.assertIn("HTTP 500",str(error))

class RouteLabelTests(unittest.TestCase):
    def test_identifiers_collapse_to_a_bounded_label(self):
        self.assertEqual(route_label("/api/v1/workflows/b934072b-3e61/runs/d02d"),"/api/v1/workflows/:id/runs/:id")
        self.assertEqual(route_label("/api/v1/workflows"),"/api/v1/workflows")
        self.assertEqual(route_label("/api/v1/workflows/x/quality-gate"),"/api/v1/workflows/:id/quality-gate")
        self.assertEqual(route_label("/"),"/")

if __name__=="__main__":unittest.main()
