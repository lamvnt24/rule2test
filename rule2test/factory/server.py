"""Unified local workspace for the typed pipeline; legacy demo remains at /legacy."""
import argparse,json,secrets,sqlite3,sys,time
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs,quote
from factory.legacy_server import Handler as LegacyHandler
from factory.api.dependencies import Application,ROOT
from factory.paths import database
from factory.api.routes.workspace import WorkspaceRoutes,Download
from factory.observability import logger,metrics,tracing
from factory.parsers.common import strict_json,ImportFailure
from factory.exceptions import NotFoundError,ConflictError,ConfigurationError,ProviderError,ValidationError

MAX_REQUEST=16*1024*1024
DRAIN_LIMIT=2*1024*1024
ASSETS={"/":("workspace.html","text/html; charset=utf-8"),
    "/workspace.js":("workspace.js","text/javascript; charset=utf-8"),"/workspace.css":("workspace.css","text/css; charset=utf-8")}
# Log and metric labels use this vocabulary only, so a workflow, document or proposal identifier
# in the request path can never become an unbounded metric dimension or reach a log line.
ROUTE_WORDS={"api","v1","workflows","proposals","batches","indexes","samples","search","suggestions","extract",
    "import","demo","session","ai-status","diagnostics","runs","evidence","sources","history","mutation",
    "quality-gate","quality-gate-report","review","promote","attach","analyze","start-review","finalize",
    "reopen-review","recover","edit-test","revise-rules","execute","legacy","workspace.js","workspace.css",
    "health","analyze-legacy","run","suites","inspect","preview","link","samples","source","rules","examples"}

def route_label(path):
    parts=[part if part in ROUTE_WORDS else ":id" for part in path.strip("/").split("/") if part]
    return "/"+"/".join(parts) if parts else "/"

class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False  # A second demo process must fail loudly instead of silently sharing the port.
    def __init__(self,address,app):
        if address[0] not in ("127.0.0.1","localhost"):raise ConfigurationError("Workspace must bind to loopback")
        self.app=app;self.csrf_token=secrets.token_urlsafe(32)
        super().__init__(address,Handler)

    def handle_error(self,request,client_address):
        """A browser that navigates away mid-response is ordinary, not an incident: record it as a
        counter instead of printing a socket traceback over the demo console. Anything else is a
        real defect and keeps the default traceback so it stays debuggable."""
        exc=sys.exc_info()[1]
        if isinstance(exc,ConnectionError):
            metrics.increment("client_disconnects_total")
            return logger.debug("client_disconnected",error_type=type(exc).__name__,outcome="error")
        logger.error("connection_failed",error_type=type(exc).__name__,outcome="error")
        super().handle_error(request,client_address)

class Handler(LegacyHandler):
    def setup(self):
        super().setup();self.connection.settimeout(20);self.last_status=0

    def log_message(self,format,*args):
        """Replaced by the structured request events below; the default stderr access line is suppressed."""

    def send_response(self,code,message=None):
        # Also covers stdlib send_error replies (400/414/501), which never reach send_bytes.
        self.last_status=code;super().send_response(code,message)

    def send_bytes(self,data,media_type,status=200,filename=None,*,legacy=False):
        self.send_response(status)
        self.send_header("Content-Type",media_type);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        trace=logger.trace_id()
        if trace:self.send_header("X-Trace-Id",trace)
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'"+(" 'unsafe-inline'" if legacy else "")+
            "; style-src 'self'"+(" 'unsafe-inline'" if legacy else "")+"; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:self.send_header("Content-Disposition","attachment; filename=download; filename*=UTF-8''"+quote(filename,safe=""))
        self.end_headers();self.wfile.write(data)

    def reply(self,value,status=200):
        self.send_bytes(json.dumps(value,ensure_ascii=False,allow_nan=False).encode("utf-8"),"application/json; charset=utf-8",status)

    def drain(self):
        """Consume a rejected request body before answering. Closing a connection while unread data
        sits in the receive buffer makes Windows abort it, and the client then never sees the error
        we just wrote. Bounded, so a rejected request cannot be used to make us read without limit."""
        if self.headers.get("Transfer-Encoding"):return
        try:length=int(self.headers.get("Content-Length","0") or 0)
        except ValueError:return
        remaining=min(max(length,0),DRAIN_LIMIT)
        while remaining>0:
            chunk=self.rfile.read(min(65536,remaining))
            if not chunk:break
            remaining-=len(chunk)

    def refuse(self,message,status):
        self.drain();return self.reply(dict(error=message),status)

    def origin_allowed(self):
        allowed={f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}
        host=self.headers.get("Host","")
        if host not in allowed:return False
        origin=self.headers.get("Origin")
        return (not origin or origin in {"http://"+h for h in allowed}) and self.headers.get("Sec-Fetch-Site")!="cross-site"

    def dispatch_error(self,exc):
        if self.last_status:
            # A response was already written (legacy routes reply and then re-raise); never write a second body.
            return logger.error("late_failure",error_type=type(exc).__name__,http_status=self.last_status,outcome="error")
        if isinstance(exc,ImportFailure):
            logger.warn("request_rejected",error_type="ImportFailure",http_status=400,count=len(exc.issues),outcome="error")
            return self.reply(dict(error="Import validation failed",issues=[x.to_dict() for x in exc.issues]),400)
        if isinstance(exc,ProviderError):
            # The operator gets the classification and a remediation hint; the provider payload is never forwarded.
            logger.error("provider_failed",error_type="ProviderError",error_kind=exc.kind,http_status=502,
                remediation=exc.remediation,outcome="error")
            metrics.increment("provider_failures_total",kind=exc.kind)
            return self.reply(dict(exc.to_dict(),trace_id=logger.trace_id()),502)
        if isinstance(exc,NotFoundError):status=404
        elif isinstance(exc,ConflictError):status=409
        elif isinstance(exc,ConfigurationError):status=503
        elif isinstance(exc,sqlite3.OperationalError):
            logger.error("database_unavailable",error_type="OperationalError",http_status=503,outcome="error")
            return self.reply(dict(error="Database is busy or locked. Close other Rule2Test processes and repeat the action; nothing was retried automatically.",
                trace_id=logger.trace_id()),503)
        elif isinstance(exc,(ValueError,TypeError,KeyError)):status=400
        else:
            logger.error("request_failed",error_type=type(exc).__name__,http_status=500,outcome="error")
            return self.reply(dict(error="Internal server error. No automatic retry was attempted.",trace_id=logger.trace_id()),500)
        logger.warn("request_rejected",error_type=type(exc).__name__,http_status=status,outcome="error")
        self.reply(dict(error=str(exc),trace_id=logger.trace_id()),status)

    def _serve(self,method,handler):
        label=route_label(urlsplit(getattr(self,"path","") or "").path)
        self.last_status=0;started=time.perf_counter()
        with tracing.trace("http_request",component="transport",method=method,route=label):
            try:handler()
            # ConnectionError covers BrokenPipeError, ConnectionResetError and the
            # ConnectionAbortedError (WinError 10053) Windows raises when a browser navigates
            # away mid-response. Writing an error body to a dead socket would only raise again.
            except ConnectionError:pass
            except Exception as exc:self.dispatch_error(exc)
            elapsed=(time.perf_counter()-started)*1000;status=str(self.last_status)
            metrics.increment("http_responses_total",method=method,route=label,status=status)
            metrics.observe("http_request_duration_ms",elapsed,method=method,route=label,status=status)
            logger.event("http_request","warn" if self.last_status>=400 else "info",method=method,route=label,
                http_status=self.last_status,duration_ms=round(elapsed,3),
                outcome="error" if self.last_status>=400 else "ok")

    def do_GET(self):self._serve("GET",self._get)
    def do_POST(self):self._serve("POST",self._post)

    def _get(self):
        if not self.origin_allowed():return self.refuse("Origin or Host denied",403)
        parsed=urlsplit(self.path);path=parsed.path
        if path=="/api/v1/session":return self.reply(dict(csrf_token=self.server.csrf_token,providers=self.server.app.providers(),api_version=1))
        if path.startswith("/api/v1/"):
            result=WorkspaceRoutes(self.server.app).get(path,parse_qs(parsed.query))
            if isinstance(result,Download):return self.send_bytes(result.data,result.media_type,filename=result.filename)
            return self.reply(result)
        if path in ASSETS:
            filename,media_type=ASSETS[path]
            return self.send_bytes((ROOT/"web"/filename).read_bytes(),media_type)
        if path=="/legacy":return self.send_bytes((ROOT/"web"/"index.html").read_bytes(),"text/html; charset=utf-8",legacy=True)
        if path.startswith("/api/"):return LegacyHandler.do_GET(self)
        return self.reply(dict(error="Not found"),404)

    def _post(self):
        if not self.origin_allowed():return self.refuse("Origin or Host denied",403)
        path=urlsplit(self.path).path
        if not path.startswith("/api/v1/"):
            if int(self.headers.get("Content-Length","0") or 0)>MAX_REQUEST:
                return self.refuse("Request exceeds the 16 MiB limit",413)
            return LegacyHandler.do_POST(self)
        token=self.headers.get("X-CSRF-Token","")
        if not secrets.compare_digest(token,self.server.csrf_token):return self.refuse("Missing or invalid session token; reload the workspace",403)
        if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":return self.refuse("Expected application/json",415)
        if self.headers.get("Transfer-Encoding"):return self.refuse("Transfer encoding is unsupported",400)
        length=int(self.headers.get("Content-Length","0"))
        if not 0<length<=MAX_REQUEST:return self.refuse("Request exceeds the 16 MiB limit or is empty",413)
        data=self.rfile.read(length)
        if len(data)!=length:return self.reply(dict(error="Incomplete request body"),400)
        body=strict_json(data.decode("utf-8"))
        return self.reply(WorkspaceRoutes(self.server.app).post(path,body))

    def do_OPTIONS(self):self.refuse("Cross-origin requests are not enabled",403)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=None)
    parser.add_argument("--port",type=int,default=8000)
    parser.add_argument("--quiet",action="store_true",help="Suppress the banner when a launcher already printed it")
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535:parser.error("Port must be 1..65535")
    diagnostics=logger.configure()
    app=Application(args.db or database())
    try:server=WorkspaceServer(("127.0.0.1",args.port),app)
    except OSError as exc:
        raise ConfigurationError(f"Port {args.port} is already in use; stop the other process or pass --port") from exc
    with server:
        logger.info("workspace_started",port=args.port,schema_version=1,
            level_configured=diagnostics["level"],destination=diagnostics["destination"])
        if not args.quiet:
            print(f"Rule2Test workspace: http://127.0.0.1:{args.port} | database: {app.db.path}",flush=True)
            print(f"Diagnostics: http://127.0.0.1:{args.port}/api/v1/diagnostics | logs: {diagnostics['destination']} at level {diagnostics['level']}",flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
if __name__=="__main__":main()
