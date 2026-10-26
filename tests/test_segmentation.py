"""Geometric segmentation must preserve measured support and missing regions."""

import json
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

from scan2mesh.demo import generate_demo
from scan2mesh.pipeline import PipelineConfig, run_pipeline
from scan2mesh.segmentation import mesh_planar_patch, segment_planar_patches


def cloud_of(points: np.ndarray) -> o3d.geometry.PointCloud:
    return o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))


def rectangular_grid(x_values, y_values, z=0.0) -> np.ndarray:
    x, y = np.meshgrid(x_values, y_values)
    return np.column_stack((x.ravel(), y.ravel(), np.full(x.size, z)))


def mesh_distances(mesh: o3d.geometry.TriangleMesh, points: np.ndarray) -> np.ndarray:
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    return scene.compute_distance(o3d.core.Tensor(points.astype(np.float32))).numpy()


def edge_crosses_rectangle(start, end, lower, upper) -> bool:
    """Clip one mesh edge against the strictly protected rectangle interior."""
    enter, leave = 0.0, 1.0
    delta = end - start
    for axis in range(2):
        if abs(delta[axis]) < 1e-12:
            if not lower[axis] < start[axis] < upper[axis]:
                return False
            continue
        crossings = sorted(
            ((lower[axis] - start[axis]) / delta[axis], (upper[axis] - start[axis]) / delta[axis])
        )
        enter = max(enter, crossings[0])
        leave = min(leave, crossings[1])
        if enter >= leave:
            return False
    return enter < leave


def test_disconnected_coplanar_boards_remain_separate_without_gap_bridges() -> None:
    axis = np.linspace(0, 1, 21)
    first = rectangular_grid(axis, axis)
    second = rectangular_grid(axis + 2, axis)
    points = np.vstack((first, second))
    cloud = cloud_of(points)

    labels, patches = segment_planar_patches(
        cloud, distance_threshold=0.005, max_planes=1, min_points=100
    )

    assert len(patches) == 2
    assert labels.shape == (len(points),)
    assert np.issubdtype(labels.dtype, np.integer)
    first_labels = set(labels[: len(first)]) - {-1}
    second_labels = set(labels[len(first) :]) - {-1}
    assert len(first_labels) == len(second_labels) == 1
    assert first_labels.isdisjoint(second_labels)
    assert np.mean(labels >= 0) >= 0.95
    for patch in patches:
        mesh = mesh_planar_patch(cloud, patch)
        vertices = np.asarray(mesh.vertices)
        assert len(mesh.triangles) > 500
        assert vertices[:, 0].max() <= 1.001 or vertices[:, 0].min() >= 1.999
        triangles = vertices[np.asarray(mesh.triangles)]
        assert np.max(np.ptp(triangles[:, :, 0], axis=1)) < 0.1
    np.testing.assert_array_equal(np.asarray(cloud.points), points)


def test_noisy_plane_projection_improves_accuracy_within_measured_tolerance() -> None:
    rng = np.random.default_rng(73)
    points = rectangular_grid(np.linspace(-1, 1, 31), np.linspace(-1, 1, 31))
    points[:, 2] = 2 + 0.2 * points[:, 0] - 0.1 * points[:, 1]
    points[:, 2] += rng.normal(0, 0.002, len(points))
    cloud = cloud_of(points)
    truth_normal = np.array([-0.2, 0.1, 1.0])
    truth_normal /= np.linalg.norm(truth_normal)
    truth_offset = -2 / np.linalg.norm([-0.2, 0.1, 1.0])

    labels, patches = segment_planar_patches(
        cloud, distance_threshold=0.01, max_planes=1, min_points=100
    )
    assert len(patches) == 1
    patch = patches[0]
    mesh = mesh_planar_patch(cloud, patch)

    raw_rms = np.sqrt(np.mean((points @ truth_normal + truth_offset) ** 2))
    projected = np.asarray(mesh.vertices)
    mesh_rms = np.sqrt(np.mean((projected @ truth_normal + truth_offset) ** 2))
    assert mesh_rms < raw_rms * 0.25
    assert 0 < patch.rms_distance < 0.003
    assert abs(np.dot(patch.normal, truth_normal)) > 0.999
    assert np.max(np.abs(projected @ patch.normal + patch.offset)) < 1e-9
    assert np.quantile(mesh_distances(mesh, points[labels >= 0]), 0.95) < 0.006
    np.testing.assert_array_equal(np.asarray(cloud.points), points)


def test_planar_window_stays_open_without_triangles_or_edges_across_it() -> None:
    points = rectangular_grid(np.linspace(-1, 1, 51), np.linspace(-1, 1, 51))
    window = (np.abs(points[:, 0]) < 0.28) & (np.abs(points[:, 1]) < 0.36)
    cloud = cloud_of(points[~window])

    labels, patches = segment_planar_patches(
        cloud, distance_threshold=0.005, max_planes=1, min_points=100
    )
    assert len(patches) == 1
    assert np.mean(labels >= 0) >= 0.95
    mesh = mesh_planar_patch(cloud, patches[0])
    vertices, triangles = np.asarray(mesh.vertices), np.asarray(mesh.triangles)
    assert len(triangles) > 2_000
    centroids = vertices[triangles].mean(axis=1)
    assert not np.any((np.abs(centroids[:, 0]) < 0.24) & (np.abs(centroids[:, 1]) < 0.32))
    edges = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges = np.unique(np.sort(edges, axis=1), axis=0)
    assert not any(
        edge_crosses_rectangle(vertices[start, :2], vertices[end, :2], [-0.24, -0.32], [0.24, 0.32])
        for start, end in edges
    )
    probes = rectangular_grid([-0.2, 0, 0.2], [-0.24, 0, 0.24])
    assert np.all(mesh_distances(mesh, probes) >= 0.07)


def test_nearby_parallel_sheets_do_not_merge_above_noise_threshold() -> None:
    rng = np.random.default_rng(83)
    axis = np.linspace(-0.5, 0.5, 21)
    first = rectangular_grid(axis, axis)
    second = rectangular_grid(axis, axis, z=0.04)
    points = np.vstack((first, second))
    points[:, 2] += rng.normal(0, 0.0005, len(points))
    cloud = cloud_of(points)

    labels, patches = segment_planar_patches(
        cloud, distance_threshold=0.004, max_planes=3, min_points=100
    )

    assert len(patches) == 2
    first_labels = set(labels[: len(first)]) - {-1}
    second_labels = set(labels[len(first) :]) - {-1}
    assert first_labels.isdisjoint(second_labels)
    assert np.mean(labels >= 0) >= 0.95
    for patch in patches:
        supported_heights = points[patch.indices, 2]
        assert np.ptp(supported_heights) < 0.005
        mesh = mesh_planar_patch(cloud, patch)
        assert np.ptp(np.asarray(mesh.vertices)[:, 2]) < 0.005


def test_curved_residual_points_remain_unknown_and_are_not_removed() -> None:
    floor = rectangular_grid(np.linspace(-1, 1, 31), np.linspace(-1, 1, 31))
    theta, height = np.meshgrid(
        np.linspace(0, 2 * np.pi, 32, endpoint=False), np.linspace(0.3, 1.5, 30)
    )
    pipe = np.column_stack(
        (2 + 0.08 * np.cos(theta.ravel()), 0.08 * np.sin(theta.ravel()), height.ravel())
    )
    points = np.vstack((floor, pipe))
    cloud = cloud_of(points)

    labels, patches = segment_planar_patches(
        cloud, distance_threshold=0.004, max_planes=1, min_points=100
    )

    assert len(patches) == 1
    assert np.all(labels[len(floor) :] == -1)
    assigned = np.concatenate([patch.indices for patch in patches])
    assert len(np.unique(assigned)) == len(assigned) == np.count_nonzero(labels >= 0)
    assert len(assigned) + np.count_nonzero(labels == -1) == len(points)
    mesh_planar_patch(cloud, patches[0])
    np.testing.assert_array_equal(np.asarray(cloud.points), points)


def test_segmented_industrial_demo_preserves_pipes_and_reports_geometric_coverage(
    tmp_path: Path,
) -> None:
    source = tmp_path / "segmented-demo.ply"
    generate_demo(source)
    original = o3d.io.read_point_cloud(str(source))
    colors = np.asarray(original.colors)
    pipe_mask = np.all(np.isclose(colors, [0.9, 0.55, 0.1], atol=0.01), axis=1)
    assert np.count_nonzero(pipe_mask) > 8_000
    output = tmp_path / "segmented-result"

    report = run_pipeline(
        source,
        output,
        PipelineConfig(surface_mode="segmented", voxel_size=0.025, plane_distance=0.015),
    )

    assert report["quality"]["original_to_mesh"]["p95"] < 0.02
    assert report["quality"]["point_to_mesh"]["p95"] < 0.02
    assert report["quality"]["mesh_to_cloud"]["p95"] < 0.08
    mesh = o3d.io.read_triangle_mesh(str(output / "mesh.ply"))
    pipe_distances = mesh_distances(mesh, np.asarray(original.points)[pipe_mask])
    assert np.mean(pipe_distances < 0.02) >= 0.95
    segmentation = report["segmentation"]
    assert segmentation["kind"] == "geometric"
    assert segmentation["mode"] == "segmented"
    assert segmentation["semantic_model"] is None
    assert segmentation["patch_count"] >= 3
    assert segmentation["unknown_points"] > 0
    assert len(segmentation["patches"]) == segmentation["patch_count"]
    assert all(patch["geometric_type"] == "plane" for patch in segmentation["patches"])
    assert all(patch["semantic_class"] is None for patch in segmentation["patches"])
    planar_points = sum(patch["point_count"] for patch in segmentation["patches"])
    assert planar_points == segmentation["planar_points"]
    assert planar_points + segmentation["unknown_points"] == report["counts"]["cleaned_points"]
    assert segmentation["label_reference"] == "cleaned.ply vertex order"
    with np.load(output / segmentation["label_file"], allow_pickle=False) as manifest:
        labels = manifest["patch_ids"]
    assert labels.dtype == np.int32
    assert labels.shape == (report["counts"]["cleaned_points"],)
    assert np.count_nonzero(labels == -1) == segmentation["unknown_points"]
    assert json.loads((output / "report.json").read_text()) == report


def test_invalid_surface_mode_is_rejected() -> None:
    with pytest.raises(ValueError):
        PipelineConfig(surface_mode="unknown")
