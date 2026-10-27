"""Standalone pipe worker for an independently installed official NKSR package.

This file is passed as Python source to the selected interpreter. It must not
import scan2mesh or rely on shared filesystem paths, including when using WSL.
"""

import io
import json
import math
import os
import platform
import sys


def _diagnose():
    info = {
        "backend": "nksr", "experimental": True, "ready": False,
        "python_version": platform.python_version(), "platform": sys.platform,
        "machine": platform.machine(), "device": "cuda:0", "model": "ks",
        "torch_version": None, "cuda_version": None, "nksr_version": None,
        "gpu_name": None, "gpu_memory_bytes": None, "errors": [],
        "license": {
            "code": "NVIDIA Source Code License; noncommercial research/evaluation only",
            "code_url": "https://github.com/nv-tlabs/NKSR/blob/public/LICENSE.txt",
            "pretrained_weights": "CC-BY-SA-4.0",
        },
    }
    if sys.platform != "linux" or platform.machine().lower() not in ("x86_64", "amd64"):
        info["errors"].append("The official NKSR build supports x86-64 Linux. On Windows use a separate WSL environment.")
    torch = nksr = None
    try:
        import torch
        info["torch_version"] = str(torch.__version__)
        info["cuda_version"] = getattr(torch.version, "cuda", None)
        if not torch.cuda.is_available():
            info["errors"].append("CUDA is unavailable in this interpreter. Check the NVIDIA driver, CUDA PyTorch build and WSL GPU access.")
        else:
            properties = torch.cuda.get_device_properties(0)
            info["gpu_name"] = str(properties.name)
            info["gpu_memory_bytes"] = int(properties.total_memory)
    except Exception as exc:
        info["errors"].append("PyTorch/CUDA could not be loaded: " + str(exc))
    try:
        import nksr
        info["nksr_version"] = str(getattr(nksr, "__version__", "unknown"))
        if not callable(getattr(nksr, "Reconstructor", None)):
            info["errors"].append("The installed nksr module does not expose the official Reconstructor API.")
    except Exception as exc:
        info["errors"].append("NKSR could not be loaded in this interpreter: " + str(exc))
    info["ready"] = not info["errors"]
    return info, torch, nksr


def _reconstruct(np, data):
    info, torch, nksr = _diagnose()
    if not info["ready"]:
        raise RuntimeError("NKSR environment is not ready. " + " ".join(info["errors"]))
    with np.load(io.BytesIO(data), allow_pickle=False) as archive:
        points = np.asarray(archive["points"], dtype=np.float64)
        normals = np.asarray(archive["normals"], dtype=np.float64)
        config = json.loads(archive["config"].item())
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3 or normals.shape != points.shape:
        raise ValueError("Expected matching N-by-3 points and normals with N >= 3")
    if not np.isfinite(points).all() or not np.isfinite(normals).all() or np.max(np.abs(points)) > np.finfo(np.float32).max:
        raise ValueError("Points and normals must be finite and fit NKSR's float32 input")
    maximum = np.max(np.abs(normals), axis=1)
    if np.any(maximum == 0):
        raise ValueError("Normals must not contain zero vectors")
    normals /= maximum[:, None]
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    detail, voxel = config["detail_level"], config["voxel_size"]
    if isinstance(detail, bool) or not isinstance(detail, (int, float)) or not math.isfinite(detail) or not 0 <= detail <= 1:
        raise ValueError("detail_level must be between 0 and 1")
    if voxel is not None and (isinstance(voxel, bool) or not isinstance(voxel, (int, float)) or not math.isfinite(voxel) or voxel <= 0):
        raise ValueError("voxel_size must be finite and positive")
    device = torch.device("cuda:0")
    xyz = torch.from_numpy(np.ascontiguousarray(points, dtype=np.float32)).to(device)
    normal = torch.from_numpy(np.ascontiguousarray(normals, dtype=np.float32)).to(device)
    # Match upstream's inference recipe; its network disables parameter
    # gradients itself. Do not impose inference_mode on its field solvers.
    # Constructing Reconstructor loads the public kitchen-sink checkpoint.
    # Diagnostics deliberately never instantiate this object.
    reconstructor = nksr.Reconstructor(device, config="ks")
    settings = {"voxel_size": float(voxel)} if voxel is not None else {"detail_level": float(detail)}
    field = reconstructor.reconstruct(xyz, normal, **settings)
    if field is None:
        raise RuntimeError("NKSR found no reconstructable surface in this excerpt")
    mesh = field.extract_dual_mesh(mise_iter=1)
    vertices = mesh.v.detach().cpu().numpy()
    triangles = mesh.f.detach().cpu().numpy()
    info.update({
        "detail_level": None if voxel is not None else float(detail),
        "voxel_size": float(voxel) if voxel is not None else None,
        "input_points": len(points), "chunking": False,
        "normal_source": "provided_oriented_normals", "inference_completed": True,
    })
    return {"vertices": vertices, "triangles": triangles, "metadata": np.asarray(json.dumps(info, allow_nan=False))}


def main():
    # Redirect file descriptor 1 itself, so C/CUDA printf and Python print both
    # go to stderr. The duplicated pipe is used only for the NPZ response.
    sys.stdout.flush()
    protocol_fd = os.dup(sys.stdout.fileno())
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    with os.fdopen(protocol_fd, "wb") as protocol:
        try:
            import numpy as np
            if sys.argv[1:] == ["--diagnose"]:
                info, _, _ = _diagnose()
                result = {"metadata": np.asarray(json.dumps(info, allow_nan=False))}
            elif sys.argv[1:] == ["--reconstruct"]:
                result = _reconstruct(np, sys.stdin.buffer.read())
            else:
                raise ValueError("Expected --diagnose or --reconstruct")
            output = io.BytesIO()
            np.savez(output, **result)
            protocol.write(output.getvalue())
            protocol.flush()
        except Exception as exc:
            detail = str(exc)
            if isinstance(exc, ModuleNotFoundError):
                detail += " Install the NKSR runtime dependencies in the interpreter selected by --nksr-python."
            if "out of memory" in detail.lower():
                detail += " Use a smaller scan excerpt or a coarser --nksr-voxel-size; no alternate mesher was used."
            print("NKSR worker: " + detail, file=sys.stderr, flush=True)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
