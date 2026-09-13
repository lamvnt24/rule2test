"""Local-demo diagnostics: structured logs, request traces and process-local metrics. Not production telemetry."""
from factory.observability.logger import configure,configuration,event,debug,info,warn,error,trace_id
from factory.observability.metrics import increment,observe,snapshot,reset
from factory.observability.tracing import trace,span,traced,current_span

__all__=["configure","configuration","event","debug","info","warn","error","trace_id",
         "increment","observe","snapshot","reset","trace","span","traced","current_span"]
