"""Single-line JSON diagnostics. A strict field allowlist keeps document text, prompts and identities out of logs."""
import contextvars,json,math,os,sys,threading
from datetime import datetime,timezone
from factory.exceptions import ConfigurationError

LEVELS=dict(debug=10,info=20,warn=30,error=40,off=100)
# Allowlist, not a denylist: an unknown key is dropped and only counted. Source text, prompts,
# model output, reviewer names, file paths and tokens therefore cannot reach a log line.
FIELDS=("span","parent","depth","duration_ms","outcome","error_type","error_kind","remediation",
    "method","path","route","http_status","component","operation","workflow_id","revision","run_id",
    "evidence_id","proposal_id","index_id","batch_id","document_hash","content_hash","report_hash",
    "status","decision","verdict","provider","model","backend","simulated","kind","count","total",
    "matched","bytes","records","candidates","queries","timeout_seconds","dimensions","port",
    "migration","schema_version","level_configured","destination")
MAX_TEXT=200
_TRACE=contextvars.ContextVar("rule2test_trace_id",default="")
_LOCK=threading.Lock()
_STATE=dict(level=LEVELS["off"],level_name="off",stream=None,destination="none",owned=False)

def _close():
    if _STATE["owned"] and _STATE["stream"] is not None:
        try:_STATE["stream"].close()
        except OSError:pass
    _STATE["stream"]=None;_STATE["owned"]=False

def configure(env=None):
    """Entry points call this explicitly; importing the library never starts logging."""
    env=os.environ if env is None else env
    name=env.get("RULE2TEST_LOG_LEVEL","info").strip().lower()
    if name not in LEVELS:raise ConfigurationError("RULE2TEST_LOG_LEVEL must be one of: "+", ".join(LEVELS))
    target=env.get("RULE2TEST_LOG_FILE","").strip()
    with _LOCK:
        _close()
        _STATE["level"]=LEVELS[name];_STATE["level_name"]=name
        if name=="off":_STATE["destination"]="none"
        elif target:
            try:_STATE["stream"]=open(target,"a",encoding="utf-8");_STATE["owned"]=True
            except OSError as exc:raise ConfigurationError("RULE2TEST_LOG_FILE cannot be opened for append") from exc
            _STATE["destination"]="file"
        else:_STATE["stream"]=sys.stderr;_STATE["destination"]="stderr"
    return configuration()

def configuration():
    return dict(level=_STATE["level_name"],destination=_STATE["destination"],allowlisted_fields=len(FIELDS),
        redaction="Field allowlist; unknown keys are dropped and only counted as dropped_fields.")

def bind(trace_id):
    return _TRACE.set(str(trace_id)[:64])

def unbind(token):
    _TRACE.reset(token)

def trace_id():
    return _TRACE.get()

def _value(value):
    if type(value) is str:return value[:MAX_TEXT]
    if type(value) is bool or type(value) is int or value is None:return value
    if type(value) is float and math.isfinite(value):return value
    return Ellipsis

def event(name,level="info",**fields):
    if LEVELS.get(level,LEVELS["info"])<_STATE["level"] or _STATE["stream"] is None:return
    record=dict(timestamp=datetime.now(timezone.utc).isoformat(),level=level,event=str(name)[:MAX_TEXT],trace_id=_TRACE.get())
    dropped=0
    for key,raw in fields.items():
        if key not in FIELDS:dropped+=1;continue
        value=_value(raw)
        if value is Ellipsis:dropped+=1;continue
        if value is not None:record[key]=value
    if dropped:record["dropped_fields"]=dropped
    line=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False)
    with _LOCK:
        stream=_STATE["stream"]
        if stream is None:return
        try:stream.write(line+"\n");stream.flush()
        except (OSError,ValueError):pass

def debug(name,**fields):event(name,"debug",**fields)
def info(name,**fields):event(name,"info",**fields)
def warn(name,**fields):event(name,"warn",**fields)
def error(name,**fields):event(name,"error",**fields)
