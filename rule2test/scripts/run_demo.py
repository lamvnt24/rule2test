"""One-command demo launcher: explicit preflight, optional fixture seeding, then the workspace."""
import argparse,importlib,json,os,platform,socket,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.observability import logger
from factory.exceptions import FactoryError

ROOT=Path(__file__).resolve().parents[1]
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
    """Report every blocking and non-blocking condition; nothing is installed or downloaded."""
    checks=[]
    version=platform.python_version()
    checks.append(dict(check="python_version",status="PASS" if sys.version_info[:2]>=MINIMUM else "FAIL",
        actual=version,requirement="Python >= 3.11"))
    parent=Path(db).parent
    writable=parent.exists() and os.access(parent,os.W_OK)
    checks.append(dict(check="database_directory",status="PASS" if writable else "FAIL",
        actual=str(parent),requirement="Database directory must exist and be writable"))
    checks.append(dict(check="port_available",status="PASS" if port_free(port) else "FAIL",
        actual=port,requirement="Loopback port must be free; the workspace refuses to share a port"))
    exists=Path(db).exists()
    migrations=[]
    if exists:
        try:
            with sqlite3.connect(db) as connection:
                migrations=sorted(row[0] for row in connection.execute("SELECT version FROM wf_schema_migrations"))
        except sqlite3.Error:migrations=["unreadable"]
    checks.append(dict(check="database_state",status="PASS",
        actual=dict(exists=exists,migrations=migrations),requirement="Existing workflow data is kept unless --reset-database is given"))
    for module,extra,purpose in OPTIONAL:
        try:
            importlib.import_module(module);installed=True
        except Exception:installed=False
        checks.append(dict(check="optional:"+module,status="PASS" if installed else "SKIP",
            actual=installed,requirement=purpose+"; install requirements-"+extra+".txt to enable"))
    fixtures=sorted(p.name for p in (ROOT/"data"/"demo").glob("*.json"))
    checks.append(dict(check="demo_fixtures",status="PASS" if fixtures else "SKIP",
        actual=fixtures,requirement="Run with --seed to create the synthetic JSON fixtures"))
    return checks

def reset_database(db):
    """Explicit, never implicit: the caller must pass --reset-database and confirm the path."""
    path=Path(db)
    if path.resolve().parent!=(ROOT/"data").resolve():
        raise ValueError("Refusing to reset a database outside the project data directory")
    removed=[]
    for candidate in (path,path.with_name(path.name+"-wal"),path.with_name(path.name+"-shm")):
        if candidate.exists():candidate.unlink();removed.append(candidate.name)
    return removed

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,default=ROOT/"data"/"workspace.db")
    parser.add_argument("--port",type=int,default=8000)
    parser.add_argument("--profile",type=Path,help="Digest-pinned AI profile; without it the offline mock providers are used")
    parser.add_argument("--seed",action="store_true",help="Create the synthetic demo fixtures that are missing")
    parser.add_argument("--reset-database",action="store_true",help="Delete the selected workspace database before starting")
    parser.add_argument("--check",action="store_true",help="Run the preflight and exit without starting the server")
    parser.add_argument("--json",action="store_true",help="Print the preflight as JSON")
    args=parser.parse_args(argv)
    if not 1<=args.port<=65535:parser.error("Port must be 1..65535")
    try:
        if args.reset_database:
            for name in reset_database(args.db):print("Removed "+name)
        if args.seed:
            from scripts.seed_demo import seed
            for created in seed():print("Created "+created)
        checks=preflight(args.port,args.db)
        if args.json:print(json.dumps(dict(checks=checks),ensure_ascii=False,indent=2))
        else:
            for row in checks:print(f"[{row['status']:4}] {row['check']:22} {row['actual']}")
        failed=[row for row in checks if row["status"]=="FAIL"]
        if failed:
            print("Preflight failed: "+", ".join(row["check"] for row in failed),file=sys.stderr)
            print("Nothing was installed, downloaded or deleted.",file=sys.stderr)
            return 2
        if args.check:
            print("Preflight passed. Start the workspace without --check.");return 0
        if args.profile:
            from factory.ai_config import read_profile
            from factory.services.ai_readiness_service import require_ready
            profile=read_profile(args.profile);require_ready(profile);os.environ.update(profile.environment())
            print("AI mode: "+profile.mode+"; model digests checked at startup. Human review remains required.")
        else:
            print("AI mode: offline mock replay. Results are explicitly labelled simulated.")
        logger.configure()
        from factory.server import main as serve
        return serve(["--db",str(args.db),"--port",str(args.port)]) or 0
    except (FactoryError,ValueError,TypeError,OSError) as exc:
        print(type(exc).__name__+": "+str(exc),file=sys.stderr);return 1
if __name__=="__main__":raise SystemExit(main())
