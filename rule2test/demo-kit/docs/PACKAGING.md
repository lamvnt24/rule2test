# Packaging — a single portable executable

`dist/rule2test.exe` is one self-contained Windows console application: a bundled CPython runtime, the
`factory` package, the browser workspace and the demo fixtures. Copy that one file to another Windows
machine and run it. Nothing is installed, no Python is required, and nothing is downloaded at startup.

## Build

```powershell
py -3 -m pip install --user pyinstaller openpyxl defusedxml
py -3 -m PyInstaller packaging/rule2test.spec --noconfirm --clean
```

Output: `dist/rule2test.exe`, about 12 MB. `make exe` runs the same command.

## Run

```powershell
.\rule2test.exe                      # preflight, start the workspace, open a browser
.\rule2test.exe --port 8010          # different port
.\rule2test.exe --no-browser         # do not open a browser
.\rule2test.exe check                # preflight only, exit 2 if a check fails
.\rule2test.exe doctor               # local model inventory
.\rule2test.exe doctor --profile data\ai_profiles\ollama.local.json --probe
.\rule2test.exe --profile data\ai_profiles\ollama.local.json   # start with a digest-pinned live AI profile
.\rule2test.exe --version
```

## Where data goes

A one-file build extracts its bundled assets into a temporary directory that the operating system
**deletes when the process exits**, so nothing writable may live there. `factory/paths.py` separates the two
roots: bundled assets are read from the extraction directory, while databases and generated artifacts are
written to the first writable location of

1. `%RULE2TEST_HOME%` if set,
2. the folder containing `rule2test.exe`,
3. `%LOCALAPPDATA%\Rule2Test`.

The workspace database is `data\workspace.db` under that root. Put the executable on a USB stick and the data
travels with it. Put it in a read-only folder and it falls back to `%LOCALAPPDATA%`. The startup banner prints
the resolved data directory every time, and `check` reports it before anything is written.

Workflows, reviews and evidence survive restarting the executable — verified by creating a workflow in one run
and reading it back in the next.

## What is in the build

| Included | Note |
| --- | --- |
| CPython runtime | No Python installation needed on the target machine |
| `factory` package, all phases | Workspace, oracle, engines, services, repositories, observability |
| `web/` workspace and `/legacy` page | Served from the extraction directory |
| `data/demo.json`, `data/demo/`, `data/ai_profiles/` | Demo fixtures and AI profile templates |
| `openpyxl`, `defusedxml` | XLSX import works out of the box |

| Excluded | Why |
| --- | --- |
| `playwright` | Needs a separate ~150 MB browser download; only used by the screenshot tooling |
| `faiss` | Large optional vector backend; the Python cosine backend is the default |
| Test suite and build tooling | Has no place in a shipped binary |

`check` reports excluded extras as `SKIP`, not as a failure.

The developer CLI scripts under `scripts/` are **not** in the executable. They are source-checkout tools; run
them with `py -3 -B scripts/<name>.py`.

## Limits, honestly

- **Windows x64 only.** PyInstaller does not cross-compile: a Linux or macOS binary must be built on that
  platform, from the same spec.
- **Unsigned.** SmartScreen will warn on first run on a machine that has not seen the file before, and some
  antivirus products flag unsigned PyInstaller binaries. Code signing is out of scope here.
- **Slower first start.** A one-file build unpacks to a temporary directory on every launch, which costs a
  second or two before the banner appears.
- Live AI still needs a local Ollama service and installed models on the target machine. Without it the build
  runs on the offline mock providers, explicitly labelled simulated.
- The executable binds loopback only and keeps every guard of the source build: session token, Host/Origin
  checks, no automatic retry, no fallback to mock, no automatic approval.

## Distribution

`dist/` is not tracked in git — a 12 MB binary that changes on every build does not belong in history. To hand
the file to someone else, copy it directly, or attach it to a GitHub release:

```powershell
gh release create v0.1.0 dist\rule2test.exe --title "Rule2Test 0.1.0" --notes "Portable Windows build"
```
