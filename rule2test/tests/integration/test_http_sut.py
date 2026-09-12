import json, threading, time, unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from factory.providers.sut.http import HttpSUTAdapter
from factory.engines.test_executor import TestExecutor
from factory.models import Action,Outcome,ExecutionStatus,Value,ValueKind
from factory.exceptions import ConfigurationError,ProviderError
from tests.fixtures.engine_cases import approved_case

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(payload)
        if self.path=="/slow": time.sleep(.1)
        if self.path=="/redirect":
            self.send_response(302);self.send_header("Location","/ok");self.end_headers();return
        status=503 if self.path=="/unavailable" else 200
        body=b"not-json" if self.path=="/bad" else Action(outcome=Outcome.ALLOW).to_json().encode()
        if self.path=="/large": body=b"x"*1000
        self.send_response(status);self.send_header("Content-Type","application/json");self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

class HttpAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.server.requests=[]
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base="http://127.0.0.1:"+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def case(self):
        return approved_case("eligibility",Value(kind=ValueKind.INTEGER,data=65),Action(outcome=Outcome.ALLOW))
    def test_real_http_pass_and_input_only_wire_contract(self):
        table,rules,test,approval=self.case()
        result=TestExecutor(HttpSUTAdapter(self.base+"/ok")).execute(test,approval,table,rules,run_id="HTTP")
        self.assertEqual(result.status,ExecutionStatus.PASS)
        self.assertEqual(set(self.server.requests[-1]),{"inputs"})
        self.assertEqual(self.server.requests[-1]["inputs"],[x.to_dict() for x in test.inputs])
    def test_http_timeout_schema_and_server_error(self):
        table,rules,test,approval=self.case()
        for path,timeout in [("/bad",1),("/unavailable",1),("/slow",.02),("/redirect",1)]:
            with self.subTest(path=path):
                result=TestExecutor(HttpSUTAdapter(self.base+path),timeout_seconds=timeout).execute(test,approval,table,rules,run_id="HTTP")
                self.assertEqual(result.status,ExecutionStatus.ERROR);self.assertIsNone(result.actual)
    def test_response_limit(self):
        _,_,test,_=self.case()
        with self.assertRaises(ProviderError):HttpSUTAdapter(self.base+"/large",max_response_bytes=100).execute(test.inputs,timeout_seconds=1)
    def test_invalid_endpoint(self):
        for endpoint in ("file:///tmp/a","http://user:password@localhost:123/","http://localhost:bad/"):
            with self.assertRaises(ConfigurationError):HttpSUTAdapter(endpoint)
