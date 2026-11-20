"""Web app locale de configuration et de flash du Pro Micro."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hmac
import logging
import secrets
import signal
import subprocess
import sys
import threading
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.serving import make_server

import device


def create_app(instance=None):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=4096, TEMPLATES_AUTO_RELOAD=True, INSTANCE=instance or secrets.token_hex(16))
    token = secrets.token_urlsafe(32)
    operation_lock = threading.Lock()
    state_lock = threading.Lock()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="usb-worker")
    app.extensions["worker"] = executor
    job = {"id": None, "kind": None, "status": "idle", "logs": [], "result": None, "error": None}

    @app.before_request
    def local_only():
        # Host validation also blocks DNS rebinding from a remote website.
        if request.host.split(":")[0] not in ("127.0.0.1", "localhost"):
            return jsonify(error="Hôte refusé. Ouvrez l’application sur 127.0.0.1."), 403
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify(error="Requête externe refusée."), 403
        origin = request.headers.get("Origin")
        if origin and urlsplit(origin).netloc != request.host:
            return jsonify(error="Origine externe refusée."), 403
        if request.method == "POST":
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", "").encode(), token.encode()):
                return jsonify(error="Session expirée. Rechargez la page."), 403
            if not request.is_json:
                return jsonify(error="Envoyez un objet JSON."), 415

    @app.after_request
    def secure_headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        return response

    @app.errorhandler(device.DeviceError)
    def device_error(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.get("/")
    def index():
        return render_template("index.html", csrf_token=token, pins=device.PINS, pin_rows=device.PIN_ROWS)

    @app.get("/api/health")
    def health():
        return jsonify(app="promicro-key", instance=app.config["INSTANCE"])

    @app.get("/api/state")
    def state():
        with state_lock:
            snapshot = {**job, "logs": list(job["logs"])}
        return jsonify(ports=device.ports(), tools=device.tool_status(), job=snapshot)

    def payload():
        data = request.get_json()
        if not isinstance(data, dict):
            raise device.DeviceError("Un objet JSON est attendu.")
        return data

    def log(message):
        with state_lock:
            job["logs"].append(str(message))
            job["logs"] = job["logs"][-150:]

    def start_job(kind, action):
        if not operation_lock.acquire(blocking=False):
            return jsonify(error="Une opération USB est déjà en cours."), 409
        job_id = secrets.token_hex(8)
        with state_lock:
            job.update(id=job_id, kind=kind, status="running", logs=[], result=None, error=None)

        def worker():
            try:
                result = action(log)
                with state_lock:
                    job.update(status="success", result=result)
            except (device.DeviceError, subprocess.SubprocessError, OSError) as error:
                with state_lock:
                    job.update(status="error", error=str(error))
            except Exception:
                # Never log request bodies or secrets, even for unexpected errors.
                with state_lock:
                    job.update(status="error", error="Erreur interne. Relancez l’application et réessayez.")
            finally:
                operation_lock.release()

        executor.submit(worker)
        return jsonify(job_id=job_id), 202

    @app.post("/api/tools")
    def install_tools():
        payload()

        def install(log):
            log("Installation locale d’Arduino CLI, des cartes et de Keyboard. Internet requis…")
            process = subprocess.run([sys.executable, str(device.ROOT / "scripts" / "install_tools.py")],
                                     cwd=device.ROOT, capture_output=True, text=True, timeout=1800)
            log((process.stdout + "\n" + process.stderr)[-24000:])
            if process.returncode:
                raise device.DeviceError("Installation incomplète. Vérifiez Internet puis relancez l’installation.")
            log("Les outils sont prêts.")
            return {"installed": True}

        return start_job("tools", install)

    @app.post("/api/flash")
    def flash():
        data = payload()
        port = device.check_port(data.get("port"))
        board = data.get("board")
        if not isinstance(board, str) or board not in device.BOARDS:
            raise device.DeviceError("Sélectionnez la variante 5 V / 16 MHz ou 3,3 V / 8 MHz.")
        return start_job("flash", lambda log: device.flash(port, board, log))

    @app.post("/api/device")
    def read_device():
        port = device.check_port(payload().get("port"))
        return start_job("info", lambda log: {"port": port, "device": device.info(port)})

    @app.post("/api/recover")
    def recover():
        data = payload()
        board = data.get("board")
        if not isinstance(board, str) or board not in device.BOARDS:
            raise device.DeviceError("Sélectionnez la variante de la carte à récupérer.")
        fresh = data.get("fresh_reset", False)
        if type(fresh) is not bool:
            raise device.DeviceError("Option de redémarrage USB invalide.")
        if fresh:
            return start_job("recover", lambda log: device.recover(board, log, timeout=180, require_disconnect=True))
        return start_job("recover", lambda log: device.recover(board, log))

    @app.post("/api/configure")
    def configure():
        data = payload()
        port = device.check_port(data.get("port"))
        settings = device.validate_settings(data, allow_keep=True)

        def save(log):
            try:
                result = device.configure(port, settings)
                log("Configuration enregistrée dans la mémoire EEPROM du Pro Micro.")
                return {"port": port, "device": result}
            finally:
                settings.clear()

        return start_job("configure", save)

    @app.post("/api/clear")
    def clear():
        port = device.check_port(payload().get("port"))

        def erase(log):
            result = device.clear(port)
            log("Mot de passe effacé. La carte ne tapera plus rien au branchement.")
            return {"port": port, "device": result}

        return start_job("clear", erase)

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--instance", default=None)
    args = parser.parse_args()
    app = create_app(args.instance)
    # Quiet access logs: configuration content is never written to the log.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    server = make_server("127.0.0.1", args.port, app, threaded=True)

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        print(f"Pro Micro Key · http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()
    finally:
        server.server_close()
        app.extensions["worker"].shutdown(wait=True)
