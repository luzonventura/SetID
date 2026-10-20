"""Construye la app de escritorio: interfaz (Vite) + ejecutables (PyInstaller).

    uv run python scripts/build_app.py              # backend/dist/SetID/SetID.exe
    uv run python scripts/build_app.py --shortcuts  # y accesos directos en Inicio y Escritorio

Los accesos directos llevan el mismo AppUserModelID que la ventana, así que al anclar SetID
a la barra de tareas se agrupa bien y conserva su icono.
"""

from __future__ import annotations

import argparse
import os
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--shortcuts", action="store_true", help="crear accesos directos")
    args = parser.parse_args()
    if not args.skip_frontend:
        build_frontend()
    build_executables()
    print(f"\nListo: {APP_DIR / 'SetID.exe'}")
    if args.shortcuts:
        create_shortcuts()


if __name__ == "__main__":
    main()
