# PyInstaller spec for Sibit.exe (one-folder build).
#
#   cd frontend && npm run build          # builds the UI into backend/sibit/web
#   .venv\Scripts\pyinstaller build\sibit.spec --noconfirm --distpath dist --workpath build\work
#
# Output: dist\Sibit\Sibit.exe  (run it; the browser opens on http://127.0.0.1:8765)
# ruff: noqa
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(ROOT, "backend")
WEB = os.path.join(BACKEND, "sibit", "web")
if not os.path.isfile(os.path.join(WEB, "index.html")):
    raise SystemExit("Frontend not built: run 'npm run build' in frontend/ first.")

datas = [(WEB, "sibit/web")]
binaries = []
hiddenimports = (
    collect_submodules("sibit")
    + collect_submodules("uvicorn")
    + ["multipart", "python_multipart"]
)
for pkg in ("ciscoconfparse2", "polars", "pymupdf", "python_calamine", "xlsxwriter"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter", "matplotlib", "IPython", "pytest", "playwright", "PIL", "fontTools",
        "pyarrow", "pandas", "numpy.distutils", "notebook", "jupyter_client",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sibit",
    icon=os.path.join(ROOT, "brand", "sibit.ico"),
    version=os.path.join(SPECPATH, "version_info.txt"),
    console=True,  # shows "Running at http://127.0.0.1:8765 — close this window to quit"
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Sibit")
