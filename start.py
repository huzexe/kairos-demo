#!/usr/bin/env python3
"""
Start Kairos with one command, on Windows, macOS or Linux:

    python start.py            (Windows may need: py start.py)

The first run creates a private Python environment in .venv, installs what
Kairos needs, and prepares the database. Later runs start in a few seconds.
Kairos then opens in your browser. Press Ctrl+C in this window to stop it.

Options:
    --port 8000      use a different port (default: first free from 8000)
    --no-browser     don't open the browser
"""

import argparse
import hashlib
import os
import socket
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
REQUIREMENTS = ROOT / "requirements.txt"
STAMP = VENV / ".kairos-requirements"
MIN_PYTHON = (3, 11)


def say(msg):
    print(f"[Kairos] {msg}", flush=True)


def ensure_environment():
    """Create .venv and install requirements when they're missing or changed."""
    if not VENV_PYTHON.exists():
        say("First run: creating a private Python environment (one time only)...")
        venv.EnvBuilder(with_pip=True).create(VENV)
    wanted = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()
    if not STAMP.exists() or STAMP.read_text().strip() != wanted:
        say("Installing what Kairos needs (this can take a minute)...")
        subprocess.check_call([str(VENV_PYTHON), "-m", "pip", "install", "--disable-pip-version-check",
                               "-q", "-r", str(REQUIREMENTS)])
        STAMP.write_text(wanted)


def free_port(start):
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("No free port found between %d and %d." % (start, start + 49))


def serve(port, open_browser):
    """Runs inside .venv: prepare the database, then serve Kairos."""
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kairos.settings")
    import django
    from django.core.management import call_command

    django.setup()
    call_command("migrate", interactive=False, verbosity=0)

    from waitress import serve as waitress_serve
    from kairos.wsgi import application

    url = f"http://127.0.0.1:{port}/"
    say(f"Kairos is running at {url}")
    say("Keep this window open while you use Kairos. Press Ctrl+C to stop.")
    if open_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    waitress_serve(application, host="127.0.0.1", port=port, threads=8, _quiet=True)


def main():
    parser = argparse.ArgumentParser(description="Start Kairos.")
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--serve", action="store_true", help=argparse.SUPPRESS)  # internal
    args = parser.parse_args()

    if sys.version_info < MIN_PYTHON:
        raise SystemExit("Kairos needs Python %d.%d or newer. Get it from https://www.python.org/downloads/" % MIN_PYTHON)

    if args.serve:
        serve(args.port, not args.no_browser)
        return

    ensure_environment()
    port = args.port or free_port(8000)
    cmd = [str(VENV_PYTHON), str(ROOT / "start.py"), "--serve", "--port", str(port)]
    if args.no_browser:
        cmd.append("--no-browser")
    try:
        sys.exit(subprocess.call(cmd, cwd=ROOT))
    except KeyboardInterrupt:
        say("Stopped.")


if __name__ == "__main__":
    main()
