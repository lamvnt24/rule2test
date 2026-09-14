"""Single entry point for the packaged application: preflight, workspace, and local AI inspection."""
import argparse,json,os,socket,sqlite3,sys,threading,webbrowser
from pathlib import Path
from factory.exceptions import FactoryError,ConfigurationError
from factory.observability import logger
from factory.paths import FROZEN,resources,workspace,database

VERSION="0.1.0"
MINIMUM=(3,11)
OPTIONAL=(("openpyxl","excel","XLSX import"),("defusedxml","excel","XLSX hardening"),
          ("faiss","retrieval","FAISS vector backend"),("playwright","browser","screenshot capture"))

def port_free(port):
    probe=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1",port));return True
    except OSError:return False
    finally:probe.close()

def preflight(port,db):
    """Report every blocking and non-blocking condition. Nothing is installed, downloaded or deleted."""
    checks=[dict(check="python_version",status="PASS" if sys.version_info[:2]>=MINIMUM else "FAIL",
        actual=".".join(str(p) for p in sys.version_info[:3])+(" (bundled)" if FROZEN else ""),
        requirement="Python >= 3.11")]
    parent=Path(db).parent
    checks.append(dict(check="data_directory",status="PASS" if parent.exists() and os.access(parent,os.W_OK) else "FAIL",
        actual=str(parent),requirement="Data directory must exist and be writable"))
    checks.append(dict(check="bundled_assets",status="PASS" if (resources()/"web"/"workspace.html").is_file() else "FAIL",
        actual=str(resources()),requirement="Browser workspace assets must be present"))
    checks.append(dict(check="port_available",status="PASS" if port_free(port) else "FAIL",
        actual=port,requirement="Loopback port must be free; the workspace refuses to share a port"))
    exists=Path(db).exists();migrations=[]
    if exists:
        try:
            with sqlite3.connect(db) as connection:
                migrations=sorted(row[0] for row in connection.execute("SELECT version FROM wf_schema_migrations"))
        except sqlite3.Error:migrations=["unreadable"]
    checks.append(dict(check="database_state",status="PASS",actual=dict(exists=exists,migrations=migrations),
        requirement="Existing workflow data is kept; this build never deletes a database"))
    for module,extra,purpose in OPTIONAL:
        try:
            __import__(module);installed=True
        except Exception:installed=False
        checks.append(dict(check="optional:"+module,status="PASS" if installed else "SKIP",
            actual=installed,requirement=purpose))
    return checks

def report(checks,as_json):
    if as_json:print(json.dumps(dict(checks=checks),ensure_ascii=False,indent=2))
    else:
        for row in checks:print(f"[{row['status']:4}] {row['check']:20} {row['actual']}")
    return [row for row in checks if row["status"]=="FAIL"]

def apply_profile(path):
    from factory.ai_config import read_profile
    from factory.services.ai_readiness_service import require_ready
    profile=read_profile(path);require_ready(profile);os.environ.update(profile.environment())
    print("AI mode: "+profile.mode+"; model digests checked at startup. Human review remains required.")

def serve(args):
    db=Path(args.db) if args.db else database()
    failed=report(preflight(args.port,db),args.json)
    if failed:
        print("Preflight failed: "+", ".join(row["check"] for row in failed),file=sys.stderr)
        print("Nothing was installed, downloaded or deleted.",file=sys.stderr)
        return 2
    if args.check:
        print("Preflight passed. Start the workspace without --check.");return 0
    if args.profile:apply_profile(args.profile)
    else:print("AI mode: offline mock replay. Results are explicitly labelled simulated.")
    diagnostics=logger.configure()
    url=f"http://127.0.0.1:{args.port}"
    print(f"Rule2Test workspace: {url}")
    print(f"Data directory:      {db.parent}")
    print(f"Diagnostics:         {url}/api/v1/diagnostics")
    print(f"Logs:                {diagnostics['destination']} at level {diagnostics['level']}")
    print("Press Ctrl+C to stop.",flush=True)
    if not args.no_browser:
        threading.Timer(1.0,lambda:webbrowser.open(url)).start()
    from factory.server import main as run
    return run(["--db",str(db),"--port",str(args.port),"--quiet"]) or 0

def doctor(args):
    from factory.services.ai_readiness_service import inventory,readiness
    if args.profile:
        from factory.ai_config import read_profile
        result=readiness(read_profile(args.profile),probe=args.probe)
    else:
        if args.probe:raise ValueError("--probe requires --profile")
        result=inventory()
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result.get("available") is False or result.get("status")=="blocked" else 0

def build_parser():
    parser=argparse.ArgumentParser(prog="rule2test",description="Rule2Test — insurance rule change to regression evidence.")
    parser.add_argument("--version",action="version",version="Rule2Test "+VERSION)
    sub=parser.add_subparsers(dest="command")
    run=sub.add_parser("serve",help="Run the browser workspace (default)")
    for target in (parser,run):
        target.add_argument("--port",type=int,default=8000)
        target.add_argument("--db",help="SQLite workspace database; defaults to data/workspace.db beside the executable")
        target.add_argument("--profile",help="Digest-pinned AI profile; without it the offline mock providers are used")
        target.add_argument("--no-browser",action="store_true",help="Do not open a browser window")
        target.add_argument("--check",action="store_true",help="Run the preflight and exit")
        target.add_argument("--json",action="store_true",help="Print the preflight as JSON")
    check=sub.add_parser("check",help="Run the preflight and exit")
    check.add_argument("--port",type=int,default=8000)
    check.add_argument("--db")
    check.add_argument("--json",action="store_true")
    inspect=sub.add_parser("doctor",help="Inspect the local model inventory or probe a profile")
    inspect.add_argument("--profile")
    inspect.add_argument("--probe",action="store_true")
    return parser

def main(argv=None):
    parser=build_parser()
    args=parser.parse_args(argv)
    try:
        if args.command=="doctor":return doctor(args)
        if args.command=="check":
            args.profile=None;args.no_browser=True;args.check=True
            return serve(args)
        if not 1<=args.port<=65535:parser.error("Port must be 1..65535")
        return serve(args)
    except KeyboardInterrupt:
        print("\nStopped.");return 0
    except (FactoryError,ValueError,TypeError,OSError) as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr);return 1

if __name__=="__main__":raise SystemExit(main())
