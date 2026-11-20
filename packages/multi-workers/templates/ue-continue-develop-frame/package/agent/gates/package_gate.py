"""Check complete UE registration/impact coverage, reproducible catalogs and package contracts."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    for command in (["agent/catalog.py", "--check"], ["agent/ask.py", "--check"], ["-m", "unittest", "discover", "-s", "agent/tests", "-v"]):
        result = subprocess.run([sys.executable, "-B", *command], cwd=ROOT)
        if result.returncode:
            sys.exit(result.returncode)
