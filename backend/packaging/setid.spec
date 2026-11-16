# -*- mode: python ; coding: utf-8 -*-
# Empaquetado con PyInstaller.
#
# Windows: una carpeta dist/SetID con
#   SetID.exe      app de escritorio (sin consola)
#   setid-cli.exe  CLI; además ejecuta yt-dlp para la app
#
# Mac: dist/SetID.app, con SetID y setid-cli en Contents/MacOS y ffmpeg/ffprobe en
# Contents/Frameworks/bin (el Mac no los trae y la app no puede pedir que se instalen).
#
# Si SETID_FFMPEG_DIR apunta a una carpeta con ffmpeg y ffprobe, se meten en el paquete
# (obligatorio en el Mac; opcional en Windows, donde se siguen buscando en el PATH).
#
# Se construye con:  uv run python scripts/build_app.py

import os
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

IS_MAC = sys.platform == "darwin"
HERE = Path(SPECPATH)
BACKEND = HERE.parent
ROOT = BACKEND.parent
SRC = BACKEND / "src"
ASSETS = SRC / "setid" / "app" / "assets"
ICON = ASSETS / ("setid.icns" if IS_MAC else "setid.ico")
FRONTEND = ROOT / "frontend" / "dist"
VERSION = re.search(
    r'__version__ = "([^"]+)"', (SRC / "setid" / "__init__.py").read_text(encoding="utf-8")
).group(1)

if not (FRONTEND / "index.html").is_file():
    raise SystemExit("Falta frontend/dist: ejecuta antes `npm run build` en frontend/.")

datas = [
    (str(FRONTEND), "frontend"),
    # Alembic carga las migraciones como archivos .py desde disco.
    (str(SRC / "setid" / "db" / "migrations"), "setid/db/migrations"),
    (str(ASSETS), "setid/app/assets"),
]

# ffmpeg y ffprobe van a la carpeta «bin» del paquete; ver setid.proc.bundled_program.
binaries = []
if ffmpeg_dir := os.environ.get("SETID_FFMPEG_DIR"):
    suffix = ".exe" if sys.platform == "win32" else ""
    for tool in ("ffmpeg", "ffprobe"):
        path = Path(ffmpeg_dir) / f"{tool}{suffix}"
        if not path.is_file():
            raise SystemExit(f"SETID_FFMPEG_DIR no contiene {path.name}")
        binaries.append((str(path), "bin"))
elif IS_MAC:
    raise SystemExit("En el Mac hay que incluir ffmpeg: define SETID_FFMPEG_DIR.")

hiddenimports = [
    *collect_submodules("setid"),
    *collect_submodules("alembic"),
    *collect_submodules("shazamio"),
    *collect_submodules("keyring.backends"),
    "sqlalchemy.dialects.sqlite",
]

common = dict(
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "mypy", "ruff"],
    noarchive=False,
)

app = Analysis([str(HERE / "app_entry.py")], binaries=binaries, **common)
cli = Analysis([str(HERE / "cli_entry.py")], **common)

# Los metadatos VERSIONINFO solo existen en Windows.
exe_extra = {} if IS_MAC else {"version": str(HERE / "version_info.txt")}

app_exe = EXE(
    PYZ(app.pure),
    app.scripts,
    [],
    exclude_binaries=True,
    name="SetID",
    console=False,
    icon=str(ICON),
    **exe_extra,
)
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="setid-cli",
    console=True,
    icon=str(ICON),
    **exe_extra,
)

coll = COLLECT(
    app_exe,
    app.binaries,
    app.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    name="SetID",
)

if IS_MAC:
    # Sin cuenta de desarrollador: PyInstaller firma el paquete «ad hoc» (sin identidad), lo
    # justo para que arranque en Apple Silicon. Gatekeeper lo bloquea la primera vez (ver
    # README, «Instalar en el Mac»).
    BUNDLE(
        coll,
        name="SetID.app",
        icon=str(ICON),
        bundle_identifier="io.github.luzonventura.setid",
        version=VERSION,
        info_plist={
            "CFBundleName": "SetID",
            "CFBundleDisplayName": "SetID",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundleDevelopmentRegion": "es",
            "LSApplicationCategoryType": "public.app-category.music",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
            "NSHumanReadableCopyright": "Uso personal",
        },
    )
