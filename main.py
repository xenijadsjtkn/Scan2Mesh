"""Open this file in VS Code and click Play to choose a scan."""

import os
import subprocess
import sys
from pathlib import Path


def project_environment(root: Path) -> Path:
    """Keep Windows dependency updates outside synchronized project folders."""
    if sys.platform == "win32":
        local_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_data) if local_data else Path.home() / "AppData" / "Local"
        return base / "Scan2Mesh" / "venv"
    return Path(root) / ".venv"


def project_uv(root: Path) -> str:
    if sys.platform == "win32":
        managed = project_environment(root).parent / "tools" / "uv.exe"
        if managed.is_file():
            return str(managed)
    return "uv"


def main():
    root = Path(__file__).resolve().parent
    environment_dir = project_environment(root)
    if Path(sys.prefix).resolve() != environment_dir.resolve():
        # Play may use a global Python, even with another scan2mesh installed.
        # Select the managed environment before importing application code.
        # The old checkout-local Windows environment is left untouched.
        python = environment_dir / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        environment = os.environ.copy()
        if sys.platform == "win32":
            environment["UV_PROJECT_ENVIRONMENT"] = str(environment_dir)
            environment.setdefault("UV_CACHE_DIR", str(environment_dir.parent / "cache" / "uv"))
            print(f"Windows-Python-Umgebung wird vorbereitet: {environment_dir}", flush=True)
        else:
            environment.setdefault("UV_CACHE_DIR", str(root / ".cache" / "uv"))
        try:
            subprocess.run([project_uv(root), "sync", "--frozen"], cwd=root, env=environment, check=True)
        except FileNotFoundError:
            raise SystemExit("uv fehlt. Einmal im Terminal installieren: winget install --id astral-sh.uv --exact; danach VS Code neu starten.") from None
        except subprocess.CalledProcessError as exc:
            raise SystemExit(exc.returncode) from None
        raise SystemExit(subprocess.run([str(python), "-m", "scan2mesh.desktop", *sys.argv[1:]], cwd=Path.cwd(), env=environment).returncode)
    from scan2mesh.desktop import main as run
    return run()


if __name__ == "__main__":
    main()
