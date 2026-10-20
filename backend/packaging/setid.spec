# -*- mode: python ; coding: utf-8 -*-
# Empaquetado con PyInstaller: una carpeta dist/SetID con
#   SetID.exe      app de escritorio (sin consola)
#   setid-cli.exe  CLI; además ejecuta yt-dlp para la app
# Se construye con:  uv run python scripts/build_app.py

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

HERE = Path(SPECPATH)
BACKEND = HERE.parent
ROOT = BACKEND.parent
SRC = BACKEND / "src"
ICON = SRC / "setid" / "app" / "assets" / "setid.ico"
FRONTEND = ROOT / "frontend" / "dist"

if not (FRONTEND / "index.html").is_file():
    raise SystemExit("Falta frontend/dist: ejecuta antes `npm run build` en frontend/.")

datas = [
    (str(FRONTEND), "frontend"),
    # Alembic carga las migraciones como archivos .py desde disco.
    (str(SRC / "setid" / "db" / "migrations"), "setid/db/migrations"),
    (str(SRC / "setid" / "app" / "assets"), "setid/app/assets"),
]

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

app = Analysis([str(HERE / "app_entry.py")], **common)
cli = Analysis([str(HERE / "cli_entry.py")], **common)

app_exe = EXE(
    PYZ(app.pure),
    app.scripts,
    [],
    exclude_binaries=True,
    name="SetID",
    console=False,
    icon=str(ICON),
    version=str(HERE / "version_info.txt"),
)
cli_exe = EXE(
    PYZ(cli.pure),
    cli.scripts,
    [],
    exclude_binaries=True,
    name="setid-cli",
    console=True,
    icon=str(ICON),
    version=str(HERE / "version_info.txt"),
)

COLLECT(
    app_exe,
    app.binaries,
    app.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    name="SetID",
)
