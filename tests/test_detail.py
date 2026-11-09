"""Desktop reconstruction retains geometry smaller than the former voxel grid."""

import json
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

from scan2mesh import desktop


def test_default_desktop_preserves_fine_surface_while_removing_outliers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A 30 mm sphere densely samples detail that the former 10 mm grid erased.
    indices = np.arange(1_500)
    z = 1 - 2 * (indices + 0.5) / len(indices)
    angle = np.pi * (3 - np.sqrt(5)) * indices
    radial = np.sqrt(1 - z * z)
    truth = 0.015 * np.column_stack((radial * np.cos(angle), radial * np.sin(angle), z))
    measured = truth + np.random.default_rng(23).normal(0, 0.00002, truth.shape)
    outliers = np.vstack((np.eye(3), -np.eye(3))) * 0.2
    points = np.vstack((measured, outliers))
    source = tmp_path / "fine-sphere.ply"
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    assert o3d.io.write_point_cloud(str(source), cloud)
    monkeypatch.setattr(desktop, "choose_scan_file", lambda: source)
    monkeypatch.setattr(desktop, "RUNS_ROOT", tmp_path / "runs")

    result = desktop.main([])

    report = json.loads((result / "report.json").read_text())
    counts = report["counts"]
    assert counts["downsampled_points"] == counts["deduplicated_points"] == len(points)
    assert counts["removed_outliers"] >= len(outliers)
    assert counts["cleaned_points"] >= 1_450
    assert counts["mesh_triangles"] > 2_500
    assert report["quality"]["non_manifold_edges"] == 0

    mesh = o3d.io.read_triangle_mesh(str(result / "mesh.ply"))
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    distances = scene.compute_distance(o3d.core.Tensor(truth.astype(np.float32))).numpy()
    assert np.quantile(distances, 0.95) < 0.0001
    radial_errors = np.abs(np.linalg.norm(np.asarray(mesh.vertices), axis=1) - 0.015)
    assert np.quantile(radial_errors, 0.95) < 0.0001
