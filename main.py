"""Open this file in VS Code and click Play to choose a scan."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
    if Path(sys.prefix).resolve() != (root / ".venv").resolve():
        # Play may use a global Python, even with another scan2mesh installed.
        # Select this checkout's environment before importing application code.
        python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        environment = os.environ.copy()
        environment.setdefault("UV_CACHE_DIR", str(root / ".cache" / "uv"))
        try:
            subprocess.run(["uv", "sync", "--frozen"], cwd=root, env=environment, check=True)
        except FileNotFoundError:
            raise SystemExit("uv fehlt. Einmal im Terminal installieren: winget install --id astral-sh.uv --exact; danach VS Code neu starten.") from None
        except subprocess.CalledProcessError as exc:
            raise SystemExit(exc.returncode) from None
        raise SystemExit(subprocess.run([str(python), "-m", "scan2mesh.desktop", *sys.argv[1:]], cwd=Path.cwd(), env=environment).returncode)
    from scan2mesh.desktop import main as run
    return run()


if __name__ == "__main__":
    main()
