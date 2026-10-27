"""Optional NKSR adapter, isolated from Scan2Mesh's Python dependencies.

Only NumPy is imported here. PyTorch and NKSR run in the selected interpreter;
the same binary pipe protocol works when that interpreter lives inside WSL.
"""

import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import numpy as np


def _worker_command(mode, python=None, wsl_distro=None):
    distro = wsl_distro if wsl_distro is not None else os.environ.get("SCAN2MESH_NKSR_WSL_DISTRO")
    interpreter = python or os.environ.get("SCAN2MESH_NKSR_PYTHON") or ("python3" if distro else sys.executable)
    if not isinstance(interpreter, str) or not interpreter.strip() or "\0" in interpreter:
        raise ValueError("nksr_python must name a Python executable, not a shell command")
    source = Path(__file__).with_name("nksr_worker.py").read_text(encoding="utf-8")
    command = [interpreter, "-u", "-c", source, mode]
    if distro:
        if not isinstance(distro, str) or "\0" in distro:
            raise ValueError("nksr_wsl_distro must be a WSL distribution name")
        command = ["wsl.exe", "--distribution", distro, "--exec", *command]
    return command


def _error_tail(stderr):
    if not stderr:
        return ""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", errors="replace")
    return stderr.strip()[-6000:]


def _run_worker(mode, payload=b"", *, python=None, wsl_distro=None, timeout=1800.0):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("NKSR timeout must be a finite positive number of seconds")
    command = _worker_command(mode, python, wsl_distro)
    try:
        result = subprocess.run(command, input=payload, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        wsl_note = (
            " With WSL, check that the Linux worker has stopped before retrying; stopping wsl.exe may leave it running."
            if command[0] == "wsl.exe" else ""
        )
        raise RuntimeError(
            f"NKSR worker exceeded {timeout:g} seconds. Use a smaller scan excerpt or increase --nksr-timeout."
            + wsl_note
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            "Could not start the NKSR worker. Configure --nksr-python with the separate NKSR Python executable; "
            "on Windows use --nksr-wsl-distro for its Linux environment. " + str(exc)
        ) from exc
    if result.returncode != 0:
        detail = _error_tail(result.stderr) or "Worker exited without an error message."
        raise RuntimeError(f"NKSR worker failed (exit {result.returncode}): {detail}")
    try:
        # Pickled object arrays are never accepted across the process boundary.
        with np.load(io.BytesIO(result.stdout), allow_pickle=False) as data:
            metadata = json.loads(data["metadata"].item())
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
            json.dumps(metadata, allow_nan=False)
            if mode == "--diagnose":
                if not isinstance(metadata.get("ready"), bool):
                    raise ValueError("diagnostic readiness is missing")
                return metadata
            vertices, triangles = data["vertices"].copy(), data["triangles"].copy()
    except (ValueError, TypeError, KeyError, EOFError, UnicodeError, zipfile.BadZipFile) as exc:
        detail = _error_tail(result.stderr)
        raise RuntimeError("NKSR worker returned an invalid result archive." + (" " + detail if detail else "")) from exc
    return vertices, triangles, metadata


def _array3(value, name, minimum):
    array = np.asarray(value)
    if array.ndim != 2 or array.shape[1] != 3 or len(array) < minimum or array.dtype.kind not in "iuf":
        raise ValueError(f"{name} must be a numeric N-by-3 array with at least {minimum} rows")
    array = np.asarray(array, dtype=np.float64)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must contain only finite coordinates")
    return array


def _validate_mesh(vertices, triangles):
    try:
        vertices = _array3(vertices, "NKSR vertices", 3)
        triangles = np.asarray(triangles)
        if triangles.ndim != 2 or triangles.shape[1] != 3 or len(triangles) == 0 or triangles.dtype.kind not in "iu":
            raise ValueError("NKSR triangles must be a nonempty integer M-by-3 array")
        if np.any(triangles >= len(vertices)) or (triangles.dtype.kind == "i" and np.any(triangles < 0)):
            raise ValueError("NKSR triangles contain out-of-range vertex indices")
        triangles = triangles.astype(np.int64)
        a, b, c = triangles.T
        if np.any((a == b) | (a == c) | (b == c)):
            raise ValueError("NKSR returned degenerate triangles with repeated indices")
        cross = np.cross(vertices[b] - vertices[a], vertices[c] - vertices[a])
        if not np.isfinite(cross).all() or np.any(np.max(np.abs(cross), axis=1) == 0):
            raise ValueError("NKSR returned degenerate or non-finite triangle geometry")
    except (ValueError, TypeError, OverflowError) as exc:
        raise RuntimeError(f"Invalid NKSR mesh: {exc}") from exc
    return vertices, triangles


def diagnose_nksr(*, python=None, wsl_distro=None, timeout=30.0):
    """Inspect the selected environment and GPU without loading model weights.

    Missing dependencies or CUDA are reported as ``ready=False`` with errors.
    Failure to start or communicate with the interpreter raises RuntimeError.
    """
    return _run_worker("--diagnose", python=python, wsl_distro=wsl_distro, timeout=timeout)


def reconstruct_nksr(
    points, normals, *, python=None, wsl_distro=None, detail_level=0.0,
    voxel_size=None, timeout=1800.0,
):
    """Reconstruct one local scan excerpt with NKSR's pretrained ``ks`` model.

    Normal directions must already be consistently oriented. ``voxel_size``
    uses the point coordinates' units and overrides ``detail_level``. No
    chunking, automatic training, CPU fallback or alternate mesher is used.
    """
    points = _array3(points, "points", 3)
    normals = _array3(normals, "normals", 3)
    if normals.shape != points.shape:
        raise ValueError("normals must have the same shape and point order as points")
    maximum = np.max(np.abs(normals), axis=1)
    if np.any(maximum == 0):
        raise ValueError("normals must not contain zero vectors")
    normals = normals / maximum[:, None]
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    if np.max(np.abs(points)) > np.finfo(np.float32).max:
        raise ValueError("points exceed NKSR's float32 range; use local coordinates")
    if isinstance(detail_level, bool) or not isinstance(detail_level, (int, float)) or not math.isfinite(detail_level) or not 0 <= detail_level <= 1:
        raise ValueError("nksr_detail_level must be between 0 and 1")
    if voxel_size is not None and (
        isinstance(voxel_size, bool) or not isinstance(voxel_size, (int, float)) or not math.isfinite(voxel_size) or voxel_size <= 0
    ):
        raise ValueError("nksr_voxel_size must be finite and positive")
    config = {"detail_level": float(detail_level), "voxel_size": float(voxel_size) if voxel_size is not None else None}
    request = io.BytesIO()
    np.savez(request, points=points, normals=normals, config=np.asarray(json.dumps(config, allow_nan=False)))
    vertices, triangles, metadata = _run_worker(
        "--reconstruct", request.getvalue(), python=python, wsl_distro=wsl_distro, timeout=timeout,
    )
    vertices, triangles = _validate_mesh(vertices, triangles)
    return vertices, triangles, metadata
