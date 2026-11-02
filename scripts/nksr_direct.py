"""Run official NKSR directly and export its geometry with source scan colors.

This script deliberately does not import Scan2Mesh, filter or downsample points,
segment the scene, validate/clean the mesh, or impose reconstruction criteria.
Only missing input normals are estimated before calling NKSR.
"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import time
from uuid import uuid4


DETAIL_LEVEL = 1.0


def run(source: Path, output_root: Path, *, units: str = "m") -> Path:
    import numpy as np
    import open3d as o3d
    import torch
    import nksr
    from scipy.spatial import cKDTree

    started = time.monotonic()

    def status(message):
        elapsed = int(time.monotonic() - started)
        print(f"[{elapsed // 60:02d}:{elapsed % 60:02d}] {message}", flush=True)

    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Punktwolke nicht gefunden: {source}")
    output = Path(output_root) / (
        "nksr-direkt-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8]
    )
    output.mkdir(parents=True, exist_ok=False)
    print(f"Eingabe: {source}\nAusgabe: {output}\nKoordinateneinheit: {units}", flush=True)
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
    xyz = torch.as_tensor(local_points * scale, dtype=torch.float32, device=device)
    normal = torch.as_tensor(np.asarray(cloud.normals), dtype=torch.float32, device=device)
    status(f"NKSR auf {torch.cuda.get_device_name(0)}; Detailstufe {DETAIL_LEVEL}; alle {point_count} Punkte ...")
    reconstructor = nksr.Reconstructor(device, config="ks")
    field = reconstructor.reconstruct(xyz, normal, detail_level=DETAIL_LEVEL)
    status("NKSR-Mesh extrahieren ...")
    extracted = field.extract_dual_mesh(mise_iter=1)
    vertices = extracted.v.detach().cpu().numpy()
    triangles = extracted.f.detach().cpu().numpy()

    # Preserve exactly what NKSR returned before color transfer or PLY serialization.
    raw_path = output / "nksr_raw.npz"
    np.savez(
        raw_path, vertices=vertices, triangles=triangles,
        coordinate_origin=origin, input_units=np.asarray(units),
        input_units_to_meters=np.asarray(scale), input_path=np.asarray(str(source)),
    )
    status(f"Rohdaten gesichert: {raw_path}")
    result = o3d.geometry.TriangleMesh(
        o3d.utility.Vector3dVector(vertices.astype(np.float64) / scale + origin),
        o3d.utility.Vector3iVector(triangles),
    )
    if has_colors:
        status("Originalfarben auf die Mesh-Eckpunkte uebertragen ...")
        tree = cKDTree(local_points)
        source_colors = np.asarray(cloud.colors)
        colors = np.empty((len(vertices), 3), dtype=np.float64)
        for start in range(0, len(vertices), 200_000):
            stop = min(start + 200_000, len(vertices))
            _, nearest = tree.query(vertices[start:stop].astype(np.float64) / scale, workers=1)
            colors[start:stop] = source_colors[nearest]
        result.vertex_colors = o3d.utility.Vector3dVector(colors)
        mesh_path = output / "mesh_colored.ply"
    else:
        status("Die Quelldatei hat keine RGB-Farben; das Mesh wird ohne Farben gespeichert.")
        mesh_path = output / "mesh_raw.ply"

    if not o3d.io.write_triangle_mesh(str(mesh_path), result, write_vertex_colors=True):
        raise OSError(f"PLY konnte nicht geschrieben werden. NKSR-Rohdaten stehen in: {raw_path}")
    run_info = {
        "input_path": str(source), "input_units": units,
        "input_units_to_meters": scale, "coordinate_origin": origin.tolist(),
        "input_points": point_count, "normal_source": normal_source,
        "model": "ks", "detail_level": DETAIL_LEVEL, "mise_iter": 1,
        "vertices": len(vertices), "triangles": len(triangles),
        "colors": "nearest original point" if has_colors else None,
        "mesh_path": str(mesh_path), "raw_path": str(raw_path),
    }
    (output / "run.json").write_text(json.dumps(run_info, indent=2), encoding="utf-8")
    status(f"Fertig: {len(vertices)} Eckpunkte, {len(triangles)} Dreiecke.")
    print(f"Mesh: {mesh_path}", flush=True)
    return mesh_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="NKSR direkt mit Originalpunkten und RGB-Export ausfuehren")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--units", choices=("m", "mm"), default="m")
    args = parser.parse_args(argv)
    return run(args.input, args.output_root, units=args.units)


if __name__ == "__main__":
    main()
