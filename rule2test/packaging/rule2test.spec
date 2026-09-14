# PyInstaller spec: one self-contained console executable.
# Build with:  py -3 -m PyInstaller packaging/rule2test.spec --noconfirm --clean
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

# Read-only assets the running application opens by path. Writable state never lives here:
# factory.paths puts databases beside the executable, because the one-file extraction
# directory is deleted when the process exits.
datas = [
    (str(ROOT / "web"), "web"),
    (str(ROOT / "data" / "demo.json"), "data"),
    (str(ROOT / "data" / "demo"), "data/demo"),
    (str(ROOT / "data" / "ai_profiles"), "data/ai_profiles"),
]

hiddenimports = [
    "factory.app",
    "factory.server",
    "factory.legacy_server",
    "factory.api.routes.workspace",
    "factory.providers.llm.mock",
    "factory.providers.llm.ollama",
    "factory.providers.embedding.mock",
    "factory.providers.embedding.ollama",
    "factory.providers.sut.mock",
    "factory.providers.sut.http",
    "factory.providers.vector.base",
    "openpyxl",
    "defusedxml",
]

# Excluded on purpose: playwright needs a separate browser download, faiss is a large optional
# backend, and the test/build toolchain has no place in a shipped binary.
excludes = [
    "playwright", "faiss", "numpy", "pytest", "unittest", "tkinter",
    "PyInstaller", "setuptools", "pip", "streamlit",
    # openpyxl imports Pillow only for images in sheets, which this application never reads.
    # pypdfium2 is a build-time verification tool. Both are several megabytes of dead weight.
    "PIL", "Pillow", "pypdfium2", "pypdfium2_raw",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="rule2test",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
