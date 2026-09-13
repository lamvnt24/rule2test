"""Unified local workspace for the typed pipeline; legacy demo remains at /legacy."""
import argparse,json,logging,secrets
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs,quote
from factory.legacy_server import Handler as LegacyHandler
from factory.api.dependencies import Application,ROOT
from factory.api.routes.workspace import WorkspaceRoutes,Download
from factory.parsers.common import strict_json,ImportFailure
from factory.exceptions import NotFoundError,ConflictError,ConfigurationError,ProviderError,ValidationError

MAX_REQUEST=16*1024*1024
ASSETS={"/":("workspace.html","text/html; charset=utf-8"),
    "/workspace.js":("workspace.js","text/javascript; charset=utf-8"),"/workspace.css":("workspace.css","text/css; charset=utf-8")}

class WorkspaceServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,app):
        if address[0] not in ("127.0.0.1","localhost"):raise ConfigurationError("Workspace must bind to loopback")
        self.app=app;self.csrf_token=secrets.token_urlsafe(32)
        super().__init__(address,Handler)

class Handler(LegacyHandler):
    def setup(self):
        super().setup();self.connection.settimeout(20)

    def log_message(self,format,*args):
        logging.info("%s %s",self.command,urlsplit(self.path).path)

    def send_bytes(self,data,media_type,status=200,filename=None,*,legacy=False):
        self.send_response(status)
        self.send_header("Content-Type",media_type);self.send_header("Content-Length",str(len(data)))
        self.send_header("Cache-Control","no-store");self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'"+(" 'unsafe-inline'" if legacy else "")+
            "; style-src 'self'"+(" 'unsafe-inline'" if legacy else "")+"; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:self.send_header("Content-Disposition","attachment; filename=download; filename*=UTF-8''"+quote(filename,safe=""))
        self.end_headers();self.wfile.write(data)

    def reply(self,value,status=200):
        self.send_bytes(json.dumps(value,ensure_ascii=False,allow_nan=False).encode("utf-8"),"application/json; charset=utf-8",status)

    def origin_allowed(self):
        allowed={f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}
        host=self.headers.get("Host","")
        if host not in allowed:return False
        origin=self.headers.get("Origin")
        return (not origin or origin in {"http://"+h for h in allowed}) and self.headers.get("Sec-Fetch-Site")!="cross-site"

    def dispatch_error(self,exc):
        if isinstance(exc,ImportFailure):return self.reply(dict(error="Import validation failed",issues=[x.to_dict() for x in exc.issues]),400)
        if isinstance(exc,NotFoundError):status=404
        elif isinstance(exc,ConflictError):status=409
        elif isinstance(exc,ProviderError):status=502
        elif isinstance(exc,ConfigurationError):status=503
        elif isinstance(exc,(ValueError,TypeError,KeyError)):status=400
        else:
            logging.error("Request failed with %s",type(exc).__name__)
            return self.reply(dict(error="Internal server error. No automatic retry was attempted."),500)
        self.reply(dict(error=str(exc)),status)

    def do_GET(self):
        try:
            if not self.origin_allowed():return self.reply(dict(error="Origin or Host denied"),403)
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
            if path.startswith("/api/"):return super().do_GET()
            return self.reply(dict(error="Not found"),404)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:self.dispatch_error(exc)

    def do_POST(self):
        try:
            if not self.origin_allowed():return self.reply(dict(error="Origin or Host denied"),403)
            path=urlsplit(self.path).path
            if not path.startswith("/api/v1/"):return super().do_POST()
            token=self.headers.get("X-CSRF-Token","")
            if not secrets.compare_digest(token,self.server.csrf_token):return self.reply(dict(error="Missing or invalid session token; reload the workspace"),403)
            if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json":return self.reply(dict(error="Expected application/json"),415)
            if self.headers.get("Transfer-Encoding"):return self.reply(dict(error="Transfer encoding is unsupported"),400)
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=MAX_REQUEST:return self.reply(dict(error="Request exceeds the 16 MiB limit or is empty"),413)
            data=self.rfile.read(length)
            if len(data)!=length:return self.reply(dict(error="Incomplete request body"),400)
            body=strict_json(data.decode("utf-8"))
            result=WorkspaceRoutes(self.server.app).post(path,body)
            return self.reply(result)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:self.dispatch_error(exc)

    def do_OPTIONS(self):self.reply(dict(error="Cross-origin requests are not enabled"),403)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"workspace.db")
    parser.add_argument("--port",type=int,default=8000)
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535:parser.error("Port must be 1..65535")
    app=Application(args.db)
    with WorkspaceServer(("127.0.0.1",args.port),app) as server:
        print(f"Rule2Test workspace: http://127.0.0.1:{args.port} | database: {app.db.path}",flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
if __name__=="__main__":main()
