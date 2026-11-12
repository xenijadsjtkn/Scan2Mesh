"""Compatibility entry point for the official NKSR direct reconstruction."""

from pathlib import Path
import sys

# The separate NKSR/WSL interpreter need not have Scan2Mesh installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scan2mesh.nksr_direct import main


if __name__ == "__main__":
    main()
