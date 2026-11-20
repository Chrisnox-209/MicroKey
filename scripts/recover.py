"""Récupération après un flash avec une fréquence incorrecte."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import device

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", required=True, choices=device.BOARDS)
    args = parser.parse_args()
    try:
        result = device.recover(args.board, lambda message: print(message, flush=True))
        print("Récupération terminée. Mot de passe enregistré : " + ("oui" if result["device"].get("configured") else "non, à configurer dans la web app"))
    except (device.DeviceError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
