"""Routes for test-case suites, their link to confirmed rules, and the demo examples."""
import base64
from factory.models.common import require
from factory.parsers.testcase_samples import sample_file,rule_examples,ROWS
from factory.services.suite_service import SuiteService,summary
from factory.services.link_service import LinkService
from factory.observability import span
from factory.exceptions import NotFoundError
from ..schemas.requests import body_keys,actor,upload

def suite_detail(suite):
    return dict(suite=suite.to_dict(),summary=summary(suite))

class SuiteRoutes:
    def __init__(self,app):self.app=app

    def get(self,path,query):
        from .workspace import Download
        app=self.app;parts=path.strip("/").split("/")
        if path=="/api/v1/rules/examples":return dict(examples=rule_examples(),synthetic=True)
        if path=="/api/v1/suites":return [summary(s) for s in SuiteService(app.db).list()]
        if len(parts)==5 and parts[3]=="samples":
            require(parts[4] in ROWS,"Unknown sample")
            name,data=sample_file(parts[4])
            return dict(filename=name,content_base64=base64.b64encode(data).decode("ascii"),synthetic=True)
        if len(parts)==4:return suite_detail(SuiteService(app.db).get(parts[3]))
        if len(parts)==5 and parts[4]=="source":
            document,data=SuiteService(app.db).source(parts[3])
            return Download(data,document.media_type,document.document_id)
        raise NotFoundError("API route not found")

    def post(self,path,body):
        from .workspace import workflow_summary
        app=self.app;parts=path.strip("/").split("/")
        if path=="/api/v1/suites/inspect":
            body_keys(body,("filename","content_base64"))
            name,data=upload(body)
            with span("suite_inspect",component="service",bytes=len(data)):return SuiteService.inspect(data,name)
        if path=="/api/v1/suites/preview":
            body_keys(body,("filename","content_base64","sheet","mapping"),("header_row",))
            name,data=upload(body)
            with span("suite_preview",component="service",bytes=len(data)):
                rows,columns=SuiteService.preview(data,name,body["sheet"],body["mapping"],body.get("header_row"))
            counts={status:sum(r.status==status for r in rows) for status in ("ready","needs_confirmation","skipped")}
            return dict(rows=[r.to_dict() for r in rows],columns=[c.to_dict() for c in columns],summary=counts)
        if path=="/api/v1/suites":
            body_keys(body,("filename","content_base64","sheet","mapping","actor"),("resolutions","header_row"));who=actor(body)
            name,data=upload(body)
            with span("suite_create",component="service",bytes=len(data)):
                suite=SuiteService(app.db).create(data,name,body["sheet"],body["mapping"],actor=who,
                    resolutions=body.get("resolutions",[]),header_row=body.get("header_row"))
            return suite_detail(suite)
        if len(parts)==5 and parts[4]=="link":
            body_keys(body,("proposal_id","proposal_hash","actor"));who=actor(body)
            with span("suite_link",component="service",suite_id=parts[3]):
                w,link=LinkService(app.db).link(parts[3],body["proposal_id"],body["proposal_hash"],actor=who)
            suite=SuiteService(app.db).get(parts[3])
            return dict(workflow=workflow_summary(w,link,suite),link=link.to_dict())
        raise NotFoundError("API route not found")
