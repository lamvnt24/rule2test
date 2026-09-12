"""Create known synthetic JSON/XLSX fixtures; existing files are preserved."""
import sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from factory.parsers.templates import PROFILES,demo_payload,json_bytes,xlsx_bytes

ROOT=Path(__file__).resolve().parents[1]
DEMO_DIR=ROOT/"data"/"demo"

def seed(directory=DEMO_DIR,*,overwrite=False):
    directory=Path(directory).resolve()
    names=tuple(profile+suffix for profile in PROFILES for suffix in (".json",".xlsx"))
    targets=[directory/name for name in names]
    # Validate every final target before writing any file, including symlink/junction escapes.
    for target in targets:
        if target.is_symlink() or target.resolve().parent!=directory:
            raise ValueError("Fixture target must remain directly inside the selected demo directory")
        if target.exists() and not target.is_file():raise ValueError("Fixture target is not a regular file")
    contents={}
    for profile in PROFILES:
        payload=demo_payload(profile)
        for suffix,encode in ((".json",json_bytes),(".xlsx",xlsx_bytes)):
            target=directory/(profile+suffix)
            if overwrite or not target.exists():contents[target]=encode(payload)
    directory.mkdir(parents=True,exist_ok=True)
    written=[]
    for target,data in contents.items():
        with target.open("wb" if overwrite else "xb") as stream:stream.write(data)
        written.append(str(target))
    return written

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--directory",type=Path,default=DEMO_DIR)
    args=parser.parse_args(argv)
    try:
        written=seed(args.directory)
        for path in written:print("Created "+path)
        print(f"{len(written)} files created; existing files preserved.")
        return 0
    except (OSError,ValueError,ImportError) as exc:print("Error: "+str(exc),file=sys.stderr);return 2

if __name__=="__main__":sys.exit(main())
