"""Run official NKSR directly and export its geometry with source scan colors.

This path deliberately does not filter or downsample points, segment the scene,
validate/clean the mesh, or impose reconstruction criteria.
Only missing input normals are estimated before calling NKSR.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import time
from uuid import uuid4


DETAIL_LEVEL = 1.0
SUPPORTED_FORMATS = {".ply", ".pcd", ".pts", ".xyz", ".xyzn", ".xyzrgb"}


def run(
    source: Path, output_root: Path, *, units: str = "m",
    detail_level: float = DETAIL_LEVEL, compare_trim: bool = True,
) -> Path:
    detail_level = float(detail_level)
    if not 0.0 <= detail_level <= 1.0:
        raise ValueError("detail_level muss zwischen 0 und 1 liegen")
    if units not in ("m", "mm"):
        raise ValueError("units muss m oder mm sein")
    source = Path(source).resolve()
    if source.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(
            "NKSR-Direkt liest PLY, PCD, PTS, XYZ, XYZN und XYZRGB. "
            "E57 und RCP/RCS zuerst als PLY oder PTS exportieren."
        )
    if not source.is_file():
        raise FileNotFoundError(f"Punktwolke nicht gefunden: {source}")

    import numpy as np
    import open3d as o3d
    from scipy.spatial import cKDTree

    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "NKSR-Direkt benoetigt PyTorch mit CUDA im ausgewaehlten Python. "
            "Unter Windows die eingerichtete NKSR-Umgebung in WSL verwenden."
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError(
            "NKSR-Direkt benoetigt eine erreichbare NVIDIA-GPU auf cuda:0. "
            "CUDA-Treiber und die PyTorch-CUDA-Installation in der NKSR-Umgebung pruefen."
        )
    try:
        import nksr
    except ImportError as exc:
        raise RuntimeError(
            "Das offizielle NKSR-Paket ist im ausgewaehlten Python nicht verfuegbar. "
            "Die eingerichtete NKSR-Umgebung mit ihren CUDA-Erweiterungen verwenden."
        ) from exc

    started = time.monotonic()

    def status(message):
        elapsed = int(time.monotonic() - started)
        print(f"[{elapsed // 60:02d}:{elapsed % 60:02d}] {message}", flush=True)

    output = Path(output_root) / (
        "nksr-direkt-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    )
    output.mkdir(parents=True, exist_ok=False)
    print(f"Eingabe: {source}\nAusgabe: {output}\nKoordinateneinheit: {units}", flush=True)
    diagnostic_path = output / "cuda_diagnostics.json"
    diagnostic_snapshots = []

    def cuda_snapshot(stage, *, point_count=None, error=None):
        """Record available CUDA evidence without masking a reconstruction error."""
        unavailable = {}

        def read_metric(name, callback):
            try:
                return callback()
            except Exception as exc:
                unavailable[name] = f"{type(exc).__name__}: {exc}"
                return None

        torch_version = read_metric("torch_version", lambda: str(torch.__version__))
        build_cuda = read_metric("torch_build_cuda", lambda: torch.version.cuda)
        gpu_name = read_metric("gpu_name", lambda: torch.cuda.get_device_name(0))
        memory = read_metric("free_total_bytes", lambda: torch.cuda.mem_get_info(0))
        allocated = read_metric("allocated_bytes", lambda: torch.cuda.memory_allocated(0))
        reserved = read_metric("reserved_bytes", lambda: torch.cuda.memory_reserved(0))
        free, total = memory if memory is not None else (None, None)
        payload = point_count * 3 * 4 if point_count is not None else None
        snapshot = {
            "stage": stage, "elapsed_seconds": round(time.monotonic() - started, 3),
            "device": "cuda:0", "torch_version": torch_version,
            "torch_build_cuda": build_cuda, "gpu_name": gpu_name,
            "free_bytes": free, "total_bytes": total,
            "allocated_bytes": allocated, "reserved_bytes": reserved,
            "input_points": point_count, "xyz_bytes": payload,
            "normal_bytes": payload,
            "total_input_tensor_bytes": 2 * payload if payload is not None else None,
            "unavailable": unavailable,
        }
        if error is not None:
            snapshot["error"] = f"{type(error).__name__}: {error}"
        diagnostic_snapshots.append(snapshot)

        def mib(value):
            return f"{value / 2**20:.2f} MiB" if value is not None else "nicht verfuegbar"

        status(f"CUDA-Diagnose [{stage}]: PyTorch {torch_version or 'nicht verfuegbar'}; Build-CUDA {build_cuda or 'nicht verfuegbar'}; GPU {gpu_name or 'nicht verfuegbar'}.")
        status(f"CUDA-Speicher [{stage}]: frei {mib(free)} / gesamt {mib(total)}; PyTorch belegt {mib(allocated)}, reserviert {mib(reserved)}.")
        for name, reason in unavailable.items():
            status(f"CUDA-Diagnose: {name} nicht verfuegbar ({reason}).")
        try:
            temporary = output / "cuda_diagnostics.json.tmp"
            temporary.write_text(json.dumps({"snapshots": diagnostic_snapshots}, indent=2), encoding="utf-8")
            temporary.replace(diagnostic_path)
            return True
        except Exception as exc:
            status(f"CUDA-Diagnose konnte nicht gespeichert werden: {diagnostic_path}: {exc}")
            return False

    cuda_snapshot("startup")
    status("Originalpunktwolke laden ...")
    cloud = o3d.io.read_point_cloud(str(source))
    if not len(cloud.points):
        raise OSError(f"Datei konnte nicht als Punktwolke eingelesen werden: {source}")
    point_count = len(cloud.points)
    has_colors = cloud.has_colors()
    status(f"{point_count} Originalpunkte; RGB-Farben: {'ja' if has_colors else 'nein'}.")

    # Reversible translation before float32 protects precision in world coordinates.
    origin = np.median(np.asarray(cloud.points), axis=0)
    cloud.translate(-origin)
    local_points = np.asarray(cloud.points)
    scale = 1.0 if units == "m" else 0.001
    normal_source = "provided"
    if cloud.has_normals():
        status("Vorhandene Normalen werden direkt verwendet.")
    else:
        normal_source = "estimated"
        status("Fehlende Normalen: Oberflaechenrichtungen schaetzen ...")
        cloud.estimate_normals()
        status("Fehlende Normalen: Oberflaechenrichtungen ausrichten ...")
        cloud.orient_normals_consistent_tangent_plane(min(30, point_count - 1))

    device = torch.device("cuda:0")
    cuda_snapshot("before_upload", point_count=point_count)
    upload_stage = "upload_positions"
    try:
        xyz = torch.as_tensor(local_points * scale, dtype=torch.float32, device=device)
        upload_stage = "upload_normals"
        normal = torch.as_tensor(np.asarray(cloud.normals), dtype=torch.float32, device=device)
    except RuntimeError as exc:
        # Shape/type errors unrelated to CUDA retain their original exception.
        reason = str(exc).lower()
        oom_type = getattr(torch.cuda, "OutOfMemoryError", None)
        is_oom = isinstance(oom_type, type) and isinstance(exc, oom_type)
        if not is_oom and "cuda" not in reason and "out of memory" not in reason:
            raise
        saved = cuda_snapshot(f"{upload_stage}_failed", point_count=point_count, error=exc)
        diagnostic_note = (
            f"CUDA-Diagnose: {diagnostic_path}"
            if saved else f"CUDA-Diagnose konnte nicht gespeichert werden: {diagnostic_path}"
        )
        raise RuntimeError(f"{exc}\nFehler beim GPU-Punkttransfer ({upload_stage}). {diagnostic_note}") from exc
    status(f"NKSR auf {torch.cuda.get_device_name(0)}; Detailstufe {detail_level}; alle {point_count} Punkte ...")
    reconstructor = nksr.Reconstructor(device, config="ks")
    field = reconstructor.reconstruct(xyz, normal, detail_level=detail_level)
    run_info = {
        "input_path": str(source), "input_units": units,
        "input_units_to_meters": scale, "coordinate_origin": origin.tolist(),
        "input_points": point_count, "normal_source": normal_source,
        "model": "ks", "detail_level": detail_level, "mise_iter": 1,
        "compare_trim": compare_trim,
        "colors": "nearest original point" if has_colors else None,
        "exports": [],
    }
    tree = None

    def export_mesh(*, trim: bool, suffix: str) -> dict:
        nonlocal tree
        status(f"NKSR-Mesh extrahieren (trim={trim}) ...")
        extracted = field.extract_dual_mesh(mise_iter=1, trim=trim)
        vertices = extracted.v.detach().cpu().numpy()
        triangles = extracted.f.detach().cpu().numpy()
        # Drop this GPU mesh before coloring and before extracting the next one.
        del extracted

        # Preserve each raw result before color transfer or PLY serialization.
        raw_path = output / f"nksr_raw{suffix}.npz"
        np.savez(
            raw_path, vertices=vertices, triangles=triangles,
            coordinate_origin=origin, input_units=np.asarray(units),
            input_units_to_meters=np.asarray(scale), input_path=np.asarray(str(source)),
            trim=np.asarray(trim), detail_level=np.asarray(detail_level),
        )
        status(f"Rohdaten gesichert: {raw_path}")
        result = o3d.geometry.TriangleMesh(
            o3d.utility.Vector3dVector(vertices.astype(np.float64) / scale + origin),
            o3d.utility.Vector3iVector(triangles),
        )
        if has_colors:
            status("Originalfarben auf die Mesh-Eckpunkte uebertragen ...")
            if tree is None:
                tree = cKDTree(local_points)
            source_colors = np.asarray(cloud.colors)
            colors = np.empty((len(vertices), 3), dtype=np.float64)
            for start in range(0, len(vertices), 200_000):
                stop = min(start + 200_000, len(vertices))
                _, nearest = tree.query(vertices[start:stop].astype(np.float64) / scale, workers=1)
                colors[start:stop] = source_colors[nearest]
            result.vertex_colors = o3d.utility.Vector3dVector(colors)
            mesh_path = output / f"mesh_colored{suffix}.ply"
        else:
            status("Die Quelldatei hat keine RGB-Farben; das Mesh wird ohne Farben gespeichert.")
            mesh_path = output / f"mesh_raw{suffix}.ply"

        if not o3d.io.write_triangle_mesh(str(mesh_path), result, write_vertex_colors=True):
            raise OSError(f"PLY konnte nicht geschrieben werden. NKSR-Rohdaten stehen in: {raw_path}")
        export_info = {
            "trim": trim, "vertices": len(vertices), "triangles": len(triangles),
            "mesh_path": str(mesh_path), "raw_path": str(raw_path),
        }
        # The caller keeps metadata only; CPU mesh arrays leave scope here.
        return export_info

    def record_export(export_info):
        run_info["exports"].append(export_info)
        if len(run_info["exports"]) == 1:
            # Keep existing readers of the primary mesh's metadata compatible.
            run_info.update(export_info)
        temporary_info = output / "run.json.tmp"
        temporary_info.write_text(json.dumps(run_info, indent=2), encoding="utf-8")
        temporary_info.replace(output / "run.json")
        status(f"Exportiert: {export_info['vertices']} Eckpunkte, {export_info['triangles']} Dreiecke.")
        print(f"Mesh (trim={export_info['trim']}): {export_info['mesh_path']}", flush=True)

    primary = export_mesh(trim=True, suffix="")
    record_export(primary)
    if compare_trim:
        record_export(export_mesh(trim=False, suffix="_untrimmed"))
    status("Fertig.")
    return Path(primary["mesh_path"])


def _detail_level_argument(value):
    try:
        level = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Detailstufe muss eine Zahl zwischen 0 und 1 sein") from exc
    if not 0.0 <= level <= 1.0:
        raise argparse.ArgumentTypeError("Detailstufe muss zwischen 0 und 1 liegen")
    return level


def main(argv=None):
    parser = argparse.ArgumentParser(description="NKSR direkt mit Originalpunkten und RGB-Export ausfuehren")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--units", choices=("m", "mm"), default="m")
    parser.add_argument("--detail-level", type=_detail_level_argument, default=DETAIL_LEVEL)
    parser.add_argument("--compare-trim", action="store_true", default=True, help="Beide NKSR-Exporte mit und ohne Maskierung speichern (Standard)")
    parser.add_argument("--result-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    primary = run(
        args.input, args.output_root, units=args.units,
        detail_level=args.detail_level, compare_trim=args.compare_trim,
    )
    if args.result_file is not None:
        args.result_file.write_text(json.dumps({"mesh_path": str(primary)}), encoding="utf-8")
    return primary


if __name__ == "__main__":
    main()
