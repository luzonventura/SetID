"""Construye la app de escritorio: interfaz (Vite) + ejecutables (PyInstaller).

    uv run python scripts/build_app.py              # backend/dist/SetID/SetID.exe
    uv run python scripts/build_app.py --shortcuts  # y accesos directos en Inicio y Escritorio

En el Mac genera ``backend/dist/SetID.app`` (con ffmpeg dentro: define ``SETID_FFMPEG_DIR``) y,
con ``--dmg``, el instalador ``backend/dist/SetID-<versión>-mac-arm64.dmg``. Para el .dmg hacen
falta ``create-dmg`` (``brew install create-dmg``) y Pillow para el fondo
(``uv run --with pillow python scripts/build_app.py --dmg``).

Los accesos directos llevan el mismo AppUserModelID que la ventana, así que al anclar SetID
a la barra de tareas se agrupa bien y conserva su icono.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"
SPEC = BACKEND / "packaging" / "setid.spec"
DIST = BACKEND / "dist"
APP_DIR = DIST / "SetID"
MAC_APP = DIST / "SetID.app"


def run(args: list[str], cwd: Path) -> None:
    print(f"› {' '.join(args)}", flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def build_frontend() -> None:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise SystemExit("No se encuentra npm: instala Node.js 22+.")
    if not (FRONTEND / "node_modules").is_dir():
        run([npm, "ci"], FRONTEND)
    run([npm, "run", "build"], FRONTEND)


def build_executables() -> None:
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(SPEC),
            "--noconfirm",
            "--clean",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BACKEND / "build"),
        ],
        BACKEND,
    )


def create_shortcuts() -> None:
    """Accesos directos de Inicio y Escritorio con el AppUserModelID de la app."""
    if sys.platform != "win32":
        return
    from setid.app.desktop import APP_USER_MODEL_ID

    target = APP_DIR / "SetID.exe"
    folders = [
        Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ["USERPROFILE"]) / "Desktop",
    ]
    for folder in folders:
        link = folder / "SetID.lnk"
        # WScript.Shell crea el .lnk; la propiedad AppUserModelID se fija con la API de
        # propiedades del shell (Shell.Application no la expone).
        script = f"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{link}')
$s.TargetPath = '{target}'
$s.WorkingDirectory = '{APP_DIR}'
$s.IconLocation = '{target},0'
$s.Description = 'SetID: extractor de tracklists'
$s.Save()
"""
        run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], BACKEND)
        _set_app_id(link, APP_USER_MODEL_ID)
        print(f"  acceso directo: {link}")


def _set_app_id(link: Path, app_id: str) -> None:
    """Escribe System.AppUserModel.ID en un .lnk mediante IPropertyStore (vía PowerShell)."""
    script = rf"""
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential, Pack = 4)] public struct PROPERTYKEY {{ public Guid fmtid; public uint pid; }}
[StructLayout(LayoutKind.Explicit)] public struct PROPVARIANT {{ [FieldOffset(0)] public ushort vt; [FieldOffset(8)] public IntPtr p; }}
[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore {{
  int GetCount(out uint c); int GetAt(uint i, out PROPERTYKEY k);
  int GetValue(ref PROPERTYKEY k, out PROPVARIANT v); int SetValue(ref PROPERTYKEY k, ref PROPVARIANT v);
  int Commit();
}}
public static class AppId {{
  [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
  static extern int SHGetPropertyStoreFromParsingName(string path, IntPtr bc, int flags, ref Guid iid, out IPropertyStore store);
  public static void Set(string path, string id) {{
    var iid = new Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"); IPropertyStore s;
    Marshal.ThrowExceptionForHR(SHGetPropertyStoreFromParsingName(path, IntPtr.Zero, 2, ref iid, out s));
    var key = new PROPERTYKEY {{ fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), pid = 5 }};
    var v = new PROPVARIANT {{ vt = 31, p = Marshal.StringToCoTaskMemUni(id) }};
    Marshal.ThrowExceptionForHR(s.SetValue(ref key, ref v)); Marshal.ThrowExceptionForHR(s.Commit());
    Marshal.FreeCoTaskMem(v.p);
  }}
}}
'@
[AppId]::Set('{link}', '{app_id}')
"""
    run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], BACKEND)


def version() -> str:
    init = (BACKEND / "src" / "setid" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__ = "([^"]+)"', init)
    if not match:
        raise SystemExit("No se encuentra __version__ en setid/__init__.py")
    return match.group(1)


def check_mac_app() -> None:
    """Comprueba que el .app está firmado (ad hoc) y que los ejecutables arrancan."""
    run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(MAC_APP)], BACKEND)
    macos = MAC_APP / "Contents" / "MacOS"
    tools = MAC_APP / "Contents" / "Frameworks" / "bin"
    run([str(macos / "setid-cli"), "--yt-dlp", "--version"], BACKEND)
    run([str(tools / "ffmpeg"), "-hide_banner", "-version"], BACKEND)
    run([str(tools / "ffprobe"), "-hide_banner", "-version"], BACKEND)


def build_dmg() -> Path:
    """Instalador .dmg con fondo propio, el icono de SetID y el acceso a Aplicaciones."""
    import make_dmg_background as bg  # junto a este script; necesita Pillow

    create_dmg = shutil.which("create-dmg")
    if not create_dmg:
        raise SystemExit("No se encuentra create-dmg: brew install create-dmg")
    work = BACKEND / "build" / "dmg"
    shutil.rmtree(work, ignore_errors=True)
    stage = work / "stage"
    stage.mkdir(parents=True)
    # ditto conserva enlaces simbólicos, permisos y la firma del paquete.
    run(["ditto", str(MAC_APP), str(stage / MAC_APP.name)], BACKEND)
    run([sys.executable, bg.__file__, str(work)], BACKEND)
    background = work / "background.tiff"
    run(
        [
            "tiffutil",
            "-cathidpicheck",
            str(work / "background.png"),
            str(work / "background@2x.png"),
            "-out",
            str(background),
        ],
        BACKEND,
    )
    dmg = DIST / f"SetID-{version()}-mac-arm64.dmg"
    args = [
        create_dmg,
        "--volname", "SetID",
        "--volicon", str(BACKEND / "src" / "setid" / "app" / "assets" / "setid.icns"),
        "--background", str(background),
        "--window-pos", "200", "120",
        "--window-size", str(bg.WIDTH), str(bg.HEIGHT),
        "--icon-size", str(bg.ICON_SIZE),
        "--text-size", str(bg.TEXT_SIZE),
        "--icon", MAC_APP.name, *map(str, bg.APP_POS),
        "--hide-extension", MAC_APP.name,
        "--app-drop-link", *map(str, bg.APPS_POS),
        "--hdiutil-quiet",
        str(dmg),
        str(stage),
    ]  # fmt: skip
    # create-dmg maqueta la ventana con AppleScript en el Finder y, en las máquinas de CI,
    # a veces falla por un tiempo de espera o un volumen que sigue ocupado: se reintenta.
    for attempt in range(1, 4):
        dmg.unlink(missing_ok=True)
        print(f"› create-dmg (intento {attempt})", flush=True)
        if subprocess.run(args, cwd=BACKEND, check=False).returncode == 0:
            break
    else:
        raise SystemExit("create-dmg falló tres veces")
    run(["hdiutil", "verify", str(dmg)], BACKEND)
    return dmg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--shortcuts", action="store_true", help="crear accesos directos")
    parser.add_argument("--dmg", action="store_true", help="crear el .dmg (solo Mac)")
    args = parser.parse_args()
    if not args.skip_frontend:
        build_frontend()
    build_executables()
    if sys.platform == "darwin":
        check_mac_app()
        print(f"\nListo: {MAC_APP}")
        if args.dmg:
            print(f"Instalador: {build_dmg()}")
        return
    print(f"\nListo: {APP_DIR / 'SetID.exe'}")
    if args.shortcuts:
        create_shortcuts()


if __name__ == "__main__":
    main()
