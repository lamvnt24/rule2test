"""Resource and writable roots, correct both from a source checkout and inside a frozen one-file build."""
import os,sys
from pathlib import Path
from factory.exceptions import ConfigurationError

FROZEN=bool(getattr(sys,"frozen",False))
_SOURCE=Path(__file__).resolve().parent.parent
PROBE=".rule2test-write-probe"

def resources():
    """Read-only bundled assets: the web pages and the shipped fixtures."""
    return Path(sys._MEIPASS) if FROZEN and hasattr(sys,"_MEIPASS") else _SOURCE

def writable(candidate):
    try:
        candidate.mkdir(parents=True,exist_ok=True)
        probe=candidate/PROBE;probe.write_bytes(b"");probe.unlink()
        return True
    except OSError:return False

def candidates():
    override=os.environ.get("RULE2TEST_HOME","").strip()
    found=[Path(override)] if override else []
    found.append(Path(sys.executable).resolve().parent)
    local=os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    found.append(Path(local)/"Rule2Test" if local else Path.home()/".rule2test")
    return found

def workspace():
    """Writable root for databases and generated artifacts. Never the one-file extraction directory,
    which the operating system deletes when the process exits."""
    if not FROZEN:return _SOURCE
    for candidate in candidates():
        if writable(candidate):return candidate
    raise ConfigurationError("No writable location for Rule2Test data; set RULE2TEST_HOME to a writable folder")

def database(name="workspace.db"):
    target=workspace()/"data"
    target.mkdir(parents=True,exist_ok=True)
    return target/name
