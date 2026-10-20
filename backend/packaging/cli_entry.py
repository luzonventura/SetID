"""Punto de entrada de setid-cli.exe (consola). También ejecuta yt-dlp para la app."""

import sys

from setid.cli import main

if __name__ == "__main__":
    sys.exit(main())
