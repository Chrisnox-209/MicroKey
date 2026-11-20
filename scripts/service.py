"""Gestion du processus local, sans tuer d’autres services sur le même port."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
STATE = RUNTIME / "server.json"


def read_state():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, ValueError):
        return None


def alive(state):
    if not state:
        return False
    try:
        os.kill(state["pid"], 0)
        # Verify identity even if the old PID has been reused.
        command = Path(f'/proc/{state["pid"]}/cmdline')
        if command.exists():
            parts = command.read_bytes().split(b"\0")
            return str(ROOT / "app.py").encode() in parts and state["instance"].encode() in parts
        return healthy(state)
    except (ProcessLookupError, PermissionError, OSError):
        return False


def healthy(state):
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{state["port"]}/api/health', timeout=0.5) as response:
            data = json.load(response)
        return data.get("app") == "promicro-key" and data.get("instance") == state["instance"]
    except (OSError, ValueError):
        return False


def start(port):
    state = read_state()
    if alive(state):
        print(f'Application déjà lancée : http://127.0.0.1:{state["port"]}')
        return
    instance = secrets.token_hex(16)
    with (RUNTIME / "server.log").open("ab") as output:
        process = subprocess.Popen([sys.executable, str(ROOT / "app.py"), "--port", str(port), "--instance", instance],
                                   cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output, stderr=output, start_new_session=True)
    state = {"pid": process.pid, "port": port, "instance": instance}
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("Démarrage impossible (port occupé ?). Consultez .runtime/server.log.")
        if healthy(state):
            STATE.write_text(json.dumps(state))
            print(f'Application lancée : http://127.0.0.1:{port}\nArrêt : make stop')
            return
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("Le serveur ne répond pas. Consultez .runtime/server.log.")


def stop():
    state = read_state()
    if not alive(state):
        STATE.unlink(missing_ok=True)
        print("Application déjà arrêtée.")
        return
    os.kill(state["pid"], signal.SIGTERM)
    for _ in range(100):
        if not alive(state):
            STATE.unlink(missing_ok=True)
            print("Application arrêtée.")
            return
        time.sleep(0.1)
    print("Arrêt demandé. L’opération Arduino en cours se termine avant la fermeture.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Le port doit être compris entre 1024 et 65535.")
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    with (RUNTIME / "service.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.action == "start":
            start(args.port)
        elif args.action == "stop":
            stop()
        else:
            state = read_state()
            print(f'Application active : http://127.0.0.1:{state["port"]}' if alive(state) else "Application arrêtée.")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
