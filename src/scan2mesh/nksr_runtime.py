"""Launch the direct NKSR worker in an existing CUDA Python environment."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


# This is static Python source, not a command assembled from scan file names.
# Each candidate is checked in a separate process so an incomplete native NKSR
# installation does not prevent testing the remaining installed environments.
_DISCOVER_PYTHON = r'''
import json
from pathlib import Path
import subprocess
import sys

base = Path.home()
candidates = [
    base / 'miniforge3/envs/nksr/bin/python',
    base / 'miniconda3/envs/nksr/bin/python',
    base / 'anaconda3/envs/nksr/bin/python',
    base / '.local/share/mamba/envs/nksr/bin/python',
    base / 'micromamba/envs/nksr/bin/python',
    Path(sys.executable),
]
found, visited = [], set()
for candidate in candidates:
    if not candidate.is_file():
        continue
    # Distinct virtual environments can symlink the same Python binary while
    # loading different packages through their own pyvenv.cfg.
    identity = str(candidate.absolute())
    if identity in visited:
        continue
    visited.add(identity)
    try:
        probe = subprocess.run(
            [str(candidate), '-c', 'import torch; import nksr'],
            capture_output=True, timeout=15,
        )
        if probe.returncode == 0:
            found.append(str(candidate))
    except (OSError, subprocess.TimeoutExpired):
        pass
print(json.dumps(found))
'''


def _capture(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, check=True, capture_output=True, text=True,
            encoding="utf-8", timeout=60,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Programm nicht gefunden: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Die Pruefung der NKSR-/WSL-Umgebung hat zu lange gedauert.") from exc
    except subprocess.CalledProcessError as exc:
        reason = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(f"NKSR-/WSL-Umgebung konnte nicht verwendet werden: {reason}") from exc
    return result.stdout.strip()


def _discover_python(prefix: list[str]) -> str:
    output = _capture([*prefix, "-c", _DISCOVER_PYTHON])
    try:
        candidates = json.loads(output)
        if not isinstance(candidates, list) or any(not isinstance(p, str) for p in candidates):
            raise ValueError("Invalid discovery result")
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Die NKSR-Python-Suche lieferte keine lesbare Interpreterliste.") from exc
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise RuntimeError(
            "Keine vorhandene NKSR-Python-Umgebung gefunden. "
            "Den absoluten Python-Pfad der eingerichteten NKSR-Umgebung mit "
            "--nksr-python oder SCAN2MESH_NKSR_PYTHON angeben. "
            "Unter Windows die WSL-Distribution mit --nksr-wsl-distro "
            "oder SCAN2MESH_NKSR_WSL_DISTRO waehlen."
        )
    raise RuntimeError(
        "Mehrere NKSR-Python-Umgebungen gefunden: " + ", ".join(candidates)
        + ". Die gewuenschte mit --nksr-python oder SCAN2MESH_NKSR_PYTHON angeben."
    )


def _wsl_path(prefix: list[str], path: str | Path, *, to_windows: bool = False) -> str:
    converted = _capture([*prefix, "wslpath", "-a", "-w" if to_windows else "-u", str(path)])
    if not converted or "\n" in converted:
        raise RuntimeError(f"WSL konnte den Dateipfad nicht eindeutig umwandeln: {path}")
    return converted


def run_direct(
    source: Path, output_root: Path, *, units: str = "m",
    python: str | None = None, wsl_distro: str | None = None,
) -> Path:
    """Run the same full-resolution NKSR reconstruction and both exports.

    A failed reconstruction is reported without selecting a different mesher or
    reducing detail. Completed and partial run artifacts remain in output_root.
    """
    source = Path(source).expanduser().resolve()
    output_root = Path(output_root).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Punktwolke nicht gefunden: {source}")
    if units not in ("m", "mm"):
        raise ValueError("units must be m or mm")
    worker = Path(__file__).resolve().parents[2] / "scripts" / "nksr_direct.py"
    if not worker.is_file():
        raise FileNotFoundError(f"NKSR-Direktstarter fehlt: {worker}")
    selected_python = python or os.environ.get("SCAN2MESH_NKSR_PYTHON")
    selected_distro = wsl_distro or os.environ.get("SCAN2MESH_NKSR_WSL_DISTRO")
    use_wsl = sys.platform == "win32" or bool(selected_distro)
    prefix: list[str] = []
    if use_wsl:
        selected_distro = selected_distro or "Ubuntu-22.04"
        prefix = ["wsl.exe", "--distribution", selected_distro, "--exec"]
        selected_python = selected_python or _discover_python([*prefix, "python3"])
        source_argument = _wsl_path(prefix, source)
        worker_argument = _wsl_path(prefix, worker)
        output_argument = _wsl_path(prefix, output_root)
    else:
        selected_python = selected_python or _discover_python([sys.executable])
        source_argument, worker_argument, output_argument = map(str, (source, worker, output_root))

    # Discovery and path conversion happen before creating any output folders.
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".nksr-launch-", dir=output_root) as temporary:
        result_file = Path(temporary) / "result.json"
        result_argument = _wsl_path(prefix, result_file) if use_wsl else str(result_file)
        command = [
            *prefix, selected_python, "-u", "-X", "utf8", worker_argument,
            "--input", source_argument, "--output-root", output_argument,
            "--units", units, "--detail-level", "1.0", "--compare-trim",
            "--result-file", result_argument,
        ]
        print(f"NKSR-Python: {selected_python}", flush=True)
        if use_wsl:
            print(f"WSL-Distribution: {selected_distro}", flush=True)
        try:
            # Preserve the worker's stage messages and allow long CUDA runs.
            subprocess.run(command, check=True)
        except FileNotFoundError as exc:
            raise RuntimeError(f"Programm nicht gefunden: {command[0]}") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"NKSR-Direktlauf fehlgeschlagen (Exitcode {exc.returncode}). "
                f"Siehe Meldung oben. Bereits geschriebene Ergebnisse bleiben unter {output_root}."
            ) from exc
        try:
            result = json.loads(result_file.read_text(encoding="utf-8"))
            mesh_name = result["mesh_path"]
            if not isinstance(mesh_name, str) or not mesh_name:
                raise ValueError("Missing mesh path")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(
                f"NKSR hat keinen lesbaren Ergebnispfad gemeldet. Ergebnisse unter {output_root} pruefen."
            ) from exc
        mesh_path = Path(_wsl_path(prefix, mesh_name, to_windows=True) if use_wsl else mesh_name)
        if not mesh_path.is_file():
            raise RuntimeError(f"NKSR meldete ein nicht erreichbares Mesh: {mesh_path}")
        return mesh_path
