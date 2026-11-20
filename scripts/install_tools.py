"""Installer localement Arduino CLI et le support officiel SparkFun."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from device import CLI_CONFIG, TOOL_DIR, cli_command, write_cli_config


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "ProMicro-Local/1"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def install():
    write_cli_config()
    binary = TOOL_DIR / "bin" / "arduino-cli"
    if not binary.exists():
        machine = platform.machine().lower()
        arch = {"x86_64": "64bit", "amd64": "64bit", "aarch64": "ARM64", "arm64": "ARM64"}.get(machine)
        system = {"Linux": "Linux", "Darwin": "macOS"}.get(platform.system())
        if not arch or not system:
            raise RuntimeError("Installation automatique : Linux/macOS 64 bits uniquement. Installez arduino-cli dans le PATH.")
        release = json.loads(download("https://api.github.com/repos/arduino/arduino-cli/releases/latest"))
        version = release["tag_name"].removeprefix("v")
        name = f"arduino-cli_{version}_{system}_{arch}.tar.gz"
        assets = {asset["name"]: asset["browser_download_url"] for asset in release["assets"]}
        checksum_name = next(name for name in assets if name.endswith("checksums.txt"))
        print(f"Téléchargement Arduino CLI {version}…", flush=True)
        archive = download(assets[name])
        checksums = download(assets[checksum_name]).decode()
        expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip("*") == name)
        if hashlib.sha256(archive).hexdigest() != expected:
            raise RuntimeError("Somme de contrôle Arduino CLI incorrecte.")
        binary.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            member = next(member for member in tar.getmembers() if Path(member.name).name == "arduino-cli" and member.isfile())
            binary.write_bytes(tar.extractfile(member).read())
        binary.chmod(0o755)
    # The SparkFun platform references the Arduino AVR core and toolchain.
    for arguments in [
        ["core", "update-index"],
        ["core", "install", "arduino:avr@1.8.7"],
        ["core", "install", "SparkFun:avr@1.1.13"],
        ["lib", "install", "Keyboard@1.0.6"],
    ]:
        subprocess.run(cli_command(*arguments), cwd=ROOT, check=True, timeout=900)
    (TOOL_DIR / "ready").write_text("1\n")
    print("Outils prêts pour les Pro Micro 5 V / 16 MHz et 3,3 V / 8 MHz.")


if __name__ == "__main__":
    try:
        install()
    except Exception as error:
        print(f"Installation impossible : {error}", file=sys.stderr)
        sys.exit(1)
