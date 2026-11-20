"""Compilation, téléversement et protocole série du Pro Micro."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import serial
from serial.tools import list_ports

ROOT = Path(__file__).resolve().parent
TOOL_DIR = ROOT / ".tools"
CLI_CONFIG = TOOL_DIR / "arduino-cli.yaml"
BOARDS = {
    "5v16": "SparkFun:avr:promicro:cpu=16MHzatmega32U4",
    "3v8": "SparkFun:avr:promicro:cpu=8MHzatmega32U4",
}
PREFIX = "PMK1 "
PINS = {**{pin: f"D{pin}" for pin in range(11)}, 14: "D14", 15: "D15", 16: "D16", 18: "A0", 19: "A1", 20: "A2", 21: "A3"}
PIN_ROWS = list(zip(
    [(1, "TX / 1"), (0, "RX / 0"), (None, "GND"), (None, "GND"), (2, "2"), (3, "3"), (4, "4"), (5, "5"), (6, "6"), (7, "7"), (8, "8"), (9, "9")],
    [(None, "RAW"), (None, "GND"), (None, "RST"), (None, "VCC"), (21, "A3"), (20, "A2"), (19, "A1"), (18, "A0"), (15, "15"), (14, "14"), (16, "16"), (10, "10")],
))
# Standard Caterina IDs advertise a fixed clock profile.
BOOTLOADERS = {
    (0x2341, 0x0036): "5v16", (0x2A03, 0x0036): "5v16",
    (0x2341, 0x0037): "5v16", (0x2A03, 0x0037): "5v16",
    (0x1B4F, 0x9205): "5v16", (0x1B4F, 0x9203): "3v8",
}
USB_PROFILES = {**BOOTLOADERS,
    (0x2341, 0x8036): "5v16", (0x2A03, 0x8036): "5v16",
    (0x2341, 0x8037): "5v16", (0x2A03, 0x8037): "5v16",
    (0x1B4F, 0x9206): "5v16", (0x1B4F, 0x9204): "3v8",
}


class DeviceError(Exception):
    pass


def ports():
    return [
        {"port": p.device, "name": p.description, "vid": p.vid, "pid": p.pid,
         "serial": p.serial_number, "location": p.location,
         "likely_promicro": p.vid in (0x2341, 0x2A03, 0x1B4F),
         "suggested_board": USB_PROFILES.get((p.vid, p.pid))}
        for p in list_ports.comports() if p.vid is not None
    ]


def check_port(port):
    if not isinstance(port, str) or port not in {p["port"] for p in ports()}:
        raise DeviceError("Port USB introuvable. Branchez la carte puis actualisez la liste.")
    return port


def write_cli_config():
    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    # JSON is valid YAML; quoting also handles spaces and '+' in project paths.
    CLI_CONFIG.write_text(json.dumps({
        "board_manager": {"additional_urls": ["https://raw.githubusercontent.com/sparkfun/Arduino_Boards/main/IDE_Board_Manager/package_sparkfun_index.json"]},
        "directories": {"data": str(TOOL_DIR / "data"), "downloads": str(TOOL_DIR / "downloads"), "user": str(TOOL_DIR / "sketchbook")},
        "updater": {"enable_notification": False},
    }))


def cli_command(*args):
    local = TOOL_DIR / "bin" / "arduino-cli"
    binary = str(local) if local.exists() else shutil.which("arduino-cli")
    if not binary:
        raise DeviceError("Arduino CLI absent. Cliquez sur « Installer les outils » ou lancez make tools.")
    return [binary, "--config-file", str(CLI_CONFIG), *args]


def tool_status():
    return {"installed": (TOOL_DIR / "ready").exists(),
            "cli": (TOOL_DIR / "bin" / "arduino-cli").exists() or bool(shutil.which("arduino-cli"))}


def validate_settings(data, allow_keep=False):
    if not isinstance(data, dict):
        raise DeviceError("Configuration JSON invalide.")
    password = data.get("password")
    if not isinstance(password, str) or not (0 if allow_keep else 1) <= len(password) <= 128:
        raise DeviceError("Le mot de passe doit contenir entre 1 et 128 caractères.")
    if any(not 32 <= ord(char) <= 126 for char in password):
        raise DeviceError("Utilisez des caractères ASCII imprimables : lettres sans accent, chiffres, espaces et symboles.")
    if data.get("layout") not in ("fr", "us"):
        raise DeviceError("Choisissez AZERTY français ou QWERTY US.")
    for key, minimum, maximum in [("delay_ms", 1000, 30000), ("interval_ms", 10, 200)]:
        if type(data.get(key)) is not int or not minimum <= data[key] <= maximum:
            raise DeviceError(f"Valeur incorrecte pour {key} ({minimum}–{maximum}).")
    if type(data.get("press_enter")) is not bool:
        raise DeviceError("L’option Entrée doit être activée ou désactivée.")
    mode, pin = data.get("trigger_mode", "usb"), data.get("trigger_pin", 4)
    if mode not in ("usb", "button", "both"):
        raise DeviceError("Choisissez un déclenchement USB, bouton ou les deux.")
    if type(pin) is not int or pin not in PINS:
        raise DeviceError("Choisissez une broche disponible sur le Pro Micro.")
    return {**{key: data[key] for key in ("password", "layout", "delay_ms", "interval_ms", "press_enter")}, "trigger_mode": mode, "trigger_pin": pin}


@contextmanager
def connect(port):
    check_port(port)
    try:
        with serial.Serial(port, 115200, timeout=0.25, write_timeout=2, exclusive=True) as connection:
            time.sleep(0.15)
            connection.reset_input_buffer()
            yield connection
    except (serial.SerialException, OSError) as error:
        if isinstance(error, PermissionError) or "Permission denied" in str(error):
            raise DeviceError("Accès USB refusé. Voir la section « Accès USB sous Linux » du README, puis reconnectez votre session.") from None
        raise DeviceError("Communication USB impossible. Fermez le moniteur série et vérifiez le câble.") from None


def exchange(connection, command, timeout=4):
    connection.write((PREFIX + command + "\n").encode("ascii"))
    connection.flush()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = connection.readline(512).decode("ascii", errors="replace").strip()
        if not line.startswith(PREFIX):
            continue
        try:
            reply = json.loads(line[len(PREFIX):])
        except ValueError:
            continue
        if not isinstance(reply, dict):
            continue
        if reply.get("error"):
            raise DeviceError("La carte a refusé la commande : " + str(reply["error"]))
        if reply.get("protocol") in (1, 2):
            return reply
    raise DeviceError("Le firmware Pro Micro Key ne répond pas. Installez-le d’abord avec « Flasher le firmware ».")


def info(port):
    with connect(port) as connection:
        return exchange(connection, "INFO")


def configure(port, settings):
    settings = validate_settings(settings, allow_keep=True)
    with connect(port) as connection:
        metadata = exchange(connection, "INFO")  # Never send a secret to an unknown sketch.
        extended = metadata.get("protocol") == 2
        keep_password = settings["password"] == ""
        if keep_password and not metadata.get("configured"):
            raise DeviceError("Saisissez un mot de passe pour la première configuration.")
        if keep_password and not extended:
            raise DeviceError("Pour conserver le mot de passe en modifiant les réglages, installez le nouveau firmware. Sinon, ressaisissez le mot de passe.")
        if not extended and settings["trigger_mode"] != "usb":
            raise DeviceError("Le mode bouton demande le nouveau firmware. Installez-le dans l’onglet Installer, puis réenregistrez la configuration.")
        command = "{} {} {} {} {} {}{}".format(
            "PARAMS" if keep_password else "SET2" if extended else "SET",
            settings["layout"], settings["delay_ms"], settings["interval_ms"],
            int(settings["press_enter"]),
            f'{settings["trigger_mode"]} {settings["trigger_pin"]} ' if extended else "",
            settings["password"].encode("ascii").hex(),
        )
        result = exchange(connection, command)
        expected_length = metadata.get("length") if keep_password else len(settings["password"])
        if not result.get("configured") or result.get("length") != expected_length:
            raise DeviceError("La carte n’a pas confirmé l’enregistrement.")
        return result


def clear(port):
    with connect(port) as connection:
        exchange(connection, "INFO")
        return exchange(connection, "CLEAR")


def run_command(command, log, timeout=180):
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        parts = [part.decode(errors="replace") if isinstance(part, bytes) else part or "" for part in (error.stdout, error.stderr)]
        if any(parts):
            log("\n".join(parts)[-18000:])
        raise DeviceError("L’outil Arduino ne répond plus. Débranchez/rebranchez le câble USB, puis relancez la récupération et le double RESET.") from None
    output = (result.stdout + "\n" + result.stderr).strip()
    if output:
        log(output[-18000:])
    if result.returncode:
        raise DeviceError("L’outil Arduino a échoué. Consultez le journal ci-dessous. Pour le bootloader, essayez un double contact RST–GND puis relancez le flash.")


def run_cli(arguments, log, timeout=180):
    return run_command(cli_command(*arguments), log, timeout)


def check_board_profile(port_info, board):
    expected = USB_PROFILES.get((port_info.get("vid"), port_info.get("pid")))
    if expected and expected != board:
        label = "5 V / 16 MHz" if expected == "5v16" else "3,3 V / 8 MHz"
        raise DeviceError(f"L’identité USB de cette carte correspond au profil {label}. Sélectionnez cette variante pour éviter de perdre la connexion USB.")


def compile_firmware(board, log):
    if board not in BOARDS:
        raise DeviceError("Variante de carte inconnue.")
    if not tool_status()["installed"]:
        raise DeviceError("Installez d’abord les outils Arduino.")
    build = ROOT / ".runtime" / "build" / board
    build.mkdir(parents=True, exist_ok=True)
    log("Compilation du firmware pour " + ("5 V / 16 MHz" if board == "5v16" else "3,3 V / 8 MHz") + "…")
    run_cli(["compile", "--fqbn", BOARDS[board], "--build-path", str(build), str(ROOT / "firmware" / "promicro_key")], log)
    return build


def flash(port, board, log):
    check_port(port)
    before = next(p for p in ports() if p["port"] == port)
    check_board_profile(before, board)
    build = compile_firmware(board, log)
    check_port(port)
    log("Téléversement USB. Ne débranchez pas la carte…")
    run_cli(["upload", "--fqbn", BOARDS[board], "--port", port, "--input-dir", str(build), str(ROOT / "firmware" / "promicro_key")], log)
    return verify_after_flash(before, log)


def verify_after_flash(before, log):
    log("Flash terminé. Recherche du port après redémarrage…")
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        candidates = [p for p in ports() if
                      (before.get("location") and p.get("location") == before["location"]) or
                      (before.get("serial") and p.get("serial") == before["serial"]) or p["port"] == before["port"]]
        for candidate in candidates:
            try:
                result = info(candidate["port"])
                log("Firmware vérifié. Vous pouvez enregistrer votre mot de passe.")
                return {"port": candidate["port"], "device": result}
            except DeviceError:
                pass
        time.sleep(0.25)
    raise DeviceError("Le flash a réussi mais le firmware n’a pas répondu après redémarrage. Actualisez les ports et reconnectez la carte.")


def recover(board, log, timeout=60, require_disconnect=False):
    build = compile_firmware(board, log)
    binaries = sorted((TOOL_DIR / "data" / "packages" / "arduino" / "tools" / "avrdude").glob("*/bin/avrdude"))
    if not binaries:
        raise DeviceError("AVRDUDE absent. Réinstallez les outils Arduino.")
    binary = binaries[-1]
    config = binary.parent.parent / "etc" / "avrdude.conf"
    firmware = build / "promicro_key.ino.hex"
    if not config.is_file() or not firmware.is_file():
        raise DeviceError("Fichiers de récupération incomplets. Réinstallez les outils puis réessayez.")
    if require_disconnect:
        log("Le port USB doit être réinitialisé : débranchez puis rebranchez le câble USB, puis faites DEUX contacts rapides entre RST et GND.")
    log(f"Récupération prête : carte branchée, faites DEUX contacts rapides entre RST et GND, ou deux appuis rapides sur le bouton RESET. Attente du bootloader pendant {timeout} secondes…")
    waiting_disconnect = require_disconnect
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        candidates = [p for p in ports() if (p.get("vid"), p.get("pid")) in BOOTLOADERS]
        if waiting_disconnect:
            if not candidates:
                waiting_disconnect = False
            time.sleep(0.1)
            continue
        if len(candidates) > 1:
            raise DeviceError("Plusieurs bootloaders détectés. Ne laissez branchée que la carte à récupérer.")
        if candidates:
            before = candidates[0]
            check_board_profile(before, board)
            log("Bootloader détecté sur " + before["port"] + ". Téléversement et vérification du firmware…")
            # Already in Caterina: do not touch 1200 baud or wait for another port.
            # -D preserves EEPROM, and verification remains enabled (no -V).
            run_command([str(binary), "-C", str(config), "-p", "atmega32u4", "-c", "avr109", "-P", before["port"],
                         "-b", "57600", "-D", "-U", f"flash:w:{firmware}:i"], log, timeout=90)
            return verify_after_flash(before, log)
        time.sleep(0.1)
    raise DeviceError("Bootloader non détecté. Relancez la récupération, puis faites deux contacts rapides entre RST et GND pendant l’attente.")
