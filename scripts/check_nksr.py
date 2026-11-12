"""Check an NKSR interpreter with a small real CUDA reconstruction, without scans."""

import argparse
from contextlib import contextmanager, redirect_stdout
import json
import os
from pathlib import Path
import sys


@contextmanager
def backend_output():
    """Keep Python and native-library messages out of the JSON protocol."""
    sys.stdout.flush()
    saved = os.dup(1)
    try:
        os.dup2(2, 1)
        with redirect_stdout(sys.stderr):
            yield
    finally:
        sys.stderr.flush()
        # C/C++ stdio may still buffer messages written while fd 1 was moved.
        try:
            import ctypes
            ctypes.CDLL(None).fflush(None)
        except (AttributeError, OSError):
            pass
        os.dup2(saved, 1)
        os.close(saved)


def check(report, *, manifest=None):
    report["stage"] = "imports"
    import numpy as np
    import open3d as o3d
    import scipy
    import torch
    import nksr

    report["versions"] = {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "torch": str(torch.__version__), "cuda": torch.version.cuda,
        "open3d": o3d.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
        "nksr": nksr.__version__,
    }
    if manifest is not None:
        expected = json.loads(Path(manifest).read_text(encoding="utf-8"))
        for package in ("python", "torch", "cuda", "open3d"):
            if report["versions"][package] != expected[package]:
                raise RuntimeError(f"{package}: erwartet {expected[package]}, installiert {report['versions'][package]}")

    report["stage"] = "cuda"
    if not torch.cuda.is_available():
        raise RuntimeError("Keine NVIDIA-CUDA-GPU sichtbar. Windows-Treiber und WSL2-GPU-Zugriff pruefen.")
    device = torch.device("cuda:0")
    report["gpu"] = torch.cuda.get_device_name(0)
    # Known normals avoid a normal-estimation dependency in the setup test.
    indices = np.arange(1_200)
    z = 1 - 2 * (indices + 0.5) / len(indices)
    angle = np.pi * (3 - np.sqrt(5)) * indices
    radial = np.sqrt(1 - z * z)
    normals = np.column_stack((radial * np.cos(angle), radial * np.sin(angle), z))
    points = normals * (1 + np.random.default_rng(7).normal(0, 0.002, (len(indices), 1)))
    xyz = torch.as_tensor(points, dtype=torch.float32, device=device)
    normal = torch.as_tensor(normals, dtype=torch.float32, device=device)

    report["stage"] = "reconstruction"
    reconstructor = nksr.Reconstructor(device, config="ks")
    field = reconstructor.reconstruct(xyz, normal, detail_level=1.0)
    if field is None:
        raise RuntimeError("NKSR hat fuer die Testkugel kein Feld erzeugt.")
    report["exports"] = []
    for trim in (True, False):
        report["stage"] = "trimmed_mesh" if trim else "untrimmed_mesh"
        mesh = field.extract_dual_mesh(mise_iter=1, trim=trim)
        vertices = mesh.v.detach().cpu().numpy()
        faces = mesh.f.detach().cpu().numpy()
        if vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all():
            raise RuntimeError("NKSR-Testmesh hat ungueltige Eckpunkte.")
        if faces.ndim != 2 or faces.shape[1] != 3 or not len(faces):
            raise RuntimeError(f"NKSR-Testmesh ist leer (trim={trim}).")
        if np.any(faces < 0) or np.any(faces >= len(vertices)):
            raise RuntimeError("NKSR-Testmesh hat ungueltige Dreiecksindizes.")
        report["exports"].append({"trim": trim, "vertices": len(vertices), "triangles": len(faces)})
        del mesh, vertices, faces
    torch.cuda.synchronize(0)
    report.update(ready=True, smoke=True, stage="complete")


def main(argv=None):
    parser = argparse.ArgumentParser(description="NKSR-Installation mit einer synthetischen Kugel auf der GPU pruefen")
    parser.add_argument("--smoke", action="store_true", help="Echte NKSR-Rekonstruktion mit beiden Maskenvarianten pruefen")
    parser.add_argument("--manifest", type=Path, help="Zusaetzlich die Versionen der verwalteten Installation pruefen")
    args = parser.parse_args(argv)
    report = {"ready": False, "smoke": False, "python": sys.executable, "stage": "arguments"}
    try:
        if not args.smoke:
            raise RuntimeError("Fuer die vollstaendige GPU-Pruefung --smoke verwenden.")
        # The caller receives exactly one JSON line; native progress stays visible.
        with backend_output():
            check(report, manifest=args.manifest)
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"NKSR-Pruefung fehlgeschlagen ({report['stage']}): {exc}", file=sys.stderr, flush=True)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
