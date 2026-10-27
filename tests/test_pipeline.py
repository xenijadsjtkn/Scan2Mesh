"""Functional checks against known geometry, without external scans or a display."""

import json
from pathlib import Path

import numpy as np
import open3d as o3d
import pye57
import pytest

from scan2mesh import pipeline
from scan2mesh.pipeline import PipelineConfig, run_pipeline
from scan2mesh.demo import generate_demo


def write_ascii_ply(path: Path, points: np.ndarray) -> None:
    """Write numeric geometry without using reconstruction helpers."""
    with path.open("w", encoding="ascii") as stream:
        stream.write(
            "ply\nformat ascii 1.0\n"
            f"element vertex {len(points)}\n"
            "property double x\nproperty double y\nproperty double z\nend_header\n"
        )
        np.savetxt(stream, points, fmt="%.12g")


def write_binary_ply(path: Path, points: np.ndarray) -> None:
    """Preserve IEEE NaN/Inf independently of ASCII number parsing."""
    header = (
        "ply\nformat binary_little_endian 1.0\n"
        f"element vertex {len(points)}\n"
        "property double x\nproperty double y\nproperty double z\nend_header\n"
    ).encode("ascii")
    path.write_bytes(header + np.asarray(points, dtype="<f8").tobytes())


@pytest.fixture
def sphere_path(tmp_path: Path) -> Path:
    # A Fibonacci sphere has reproducible, nearly uniform spacing and no poles
    # with duplicate samples. Its known unit radius makes distance checks useful.
    indices = np.arange(2_000)
    z = 1 - 2 * (indices + 0.5) / len(indices)
    angle = np.pi * (3 - np.sqrt(5)) * indices
    radius = np.sqrt(1 - z * z)
    points = np.column_stack((radius * np.cos(angle), radius * np.sin(angle), z))
    path = tmp_path / "sphere.ply"
    write_ascii_ply(path, points)
    return path


@pytest.mark.parametrize(
    "ply_writer", [write_ascii_ply, write_binary_ply], ids=["ascii", "binary"]
)
def test_cleanup_preserves_plane_and_removes_bad_measurements(
    tmp_path: Path, ply_writer
) -> None:
    rng = np.random.default_rng(7)
    axis = np.linspace(-0.5, 0.5, 31)
    x, y = np.meshgrid(axis, axis)
    plane = np.column_stack((x.ravel(), y.ravel(), rng.normal(0, 0.0005, x.size)))
    distant_points = np.vstack((np.eye(3), -np.eye(3))) * 10
    points = np.vstack(
        (plane, plane[:10], distant_points, [[np.nan, 0, 0], [0, np.inf, 0]])
    )
    source = tmp_path / "noisy-plane.ply"
    ply_writer(source, points)
    output = tmp_path / "plane-result"

    report = run_pipeline(
        source,
        output,
        PipelineConfig(max_planes=1, plane_distance=0.005, ball_radius=0.06),
    )

    assert report["counts"]["input_points"] == len(points)
    assert report["counts"]["finite_points"] == len(points) - 2
    assert report["counts"]["removed_outliers"] >= len(distant_points)
    assert 800 <= report["counts"]["cleaned_points"] <= len(plane)
    cleaned = np.asarray(o3d.io.read_point_cloud(str(output / "cleaned.ply")).points)
    assert np.isfinite(cleaned).all()
    assert len(np.unique(cleaned, axis=0)) == len(cleaned)
    assert np.abs(cleaned).max() < 0.6

    assert len(report["planes"]) == 1
    detected = report["planes"][0]
    assert detected["point_count"] >= 800
    assert abs(detected["normal"][2]) > 0.999
    assert abs(detected["offset"]) < 0.002
    assert detected["rms_distance"] < 0.002


@pytest.mark.parametrize("reconstruction", ["ball-pivoting", "poisson"])
def test_reconstructs_sphere_and_reports_both_distance_directions(
    tmp_path: Path, sphere_path: Path, reconstruction: str
) -> None:
    output = tmp_path / reconstruction
    report = run_pipeline(
        sphere_path,
        output,
        PipelineConfig(reconstruction=reconstruction, max_planes=0, poisson_depth=6),
    )

    assert report["counts"]["mesh_vertices"] > 1_000
    assert report["counts"]["mesh_triangles"] > 2_000
    assert report["planes"] == []
    for direction in ("point_to_mesh", "mesh_to_cloud"):
        distances = report["quality"][direction]
        assert 0 <= distances["median"] <= distances["p95"] <= distances["max"]
        assert np.isfinite(list(distances.values())).all()
        assert distances["p95"] < 0.08

    assert report["quality"]["connected_components"] >= 1
    assert report["quality"]["boundary_edges"] >= 0
    assert report["quality"]["non_manifold_edges"] >= 0
    assert isinstance(report["quality"]["watertight"], bool)
    for filename in ("cleaned.ply", "segments.ply", "mesh.ply", "report.json"):
        assert (output / filename).stat().st_size > 0
    saved = json.loads((output / "report.json").read_text())
    assert saved == report
    mesh = o3d.io.read_triangle_mesh(str(output / "mesh.ply"))
    assert len(mesh.triangles) == report["counts"]["mesh_triangles"]
    assert np.isfinite(np.asarray(mesh.vertices)).all()


@pytest.mark.parametrize(
    "invalid",
    [
        {"voxel_size": -0.01},
        {"outlier_neighbors": 0},
        {"outlier_std_ratio": 0},
        {"plane_distance": 0},
        {"max_planes": -1},
        {"min_plane_points": 0},
        {"normal_radius": -0.1},
        {"ball_radius": 0},
        {"poisson_depth": 0},
        {"reconstruction": "unknown"},
        {"crop": (0, 0, 0, 1, 1)},
        {"crop": (0, 0, 0, 0, 1, 1)},
        {"crop": (0, 0, 0, 1, -1, 1)},
        {"crop": (0, 0, 0, 1, 1, np.inf)},
        {"crop": (np.nan, 0, 0, 1, 1, 1)},
    ],
)
def test_rejects_invalid_configuration(invalid: dict) -> None:
    with pytest.raises(ValueError):
        PipelineConfig(**invalid)


def test_does_not_overwrite_existing_results(tmp_path: Path, sphere_path: Path) -> None:
    output = tmp_path / "existing-result"
    output.mkdir()
    marker = output / "mesh.ply"
    marker.write_bytes(b"existing work\n")

    with pytest.raises((ValueError, FileExistsError)):
        run_pipeline(sphere_path, output, PipelineConfig())

    assert marker.read_bytes() == b"existing work\n"
    assert sorted(path.name for path in output.iterdir()) == ["mesh.ply"]


def test_rejects_input_directory_as_output(sphere_path: Path) -> None:
    original = sphere_path.read_bytes()

    with pytest.raises((ValueError, FileExistsError)):
        run_pipeline(sphere_path, sphere_path.parent, PipelineConfig())

    assert sphere_path.read_bytes() == original


def test_rejects_empty_point_cloud(tmp_path: Path) -> None:
    source = tmp_path / "empty.ply"
    write_ascii_ply(source, np.empty((0, 3)))

    with pytest.raises(ValueError):
        run_pipeline(source, tmp_path / "empty-result", PipelineConfig())


def test_large_site_coordinates_preserve_geometry_and_distance_accuracy(
    tmp_path: Path, sphere_path: Path
) -> None:
    shift = np.array([450_000.0, 5_800_000.0, 120.0])
    original = o3d.io.read_point_cloud(str(sphere_path))
    shifted = tmp_path / "site-sphere.ply"
    write_ascii_ply(shifted, np.asarray(original.points) + shift)
    output = tmp_path / "site-result"

    report = run_pipeline(shifted, output, PipelineConfig(max_planes=0))

    for filename, reader in (
        ("cleaned.ply", o3d.io.read_point_cloud),
        ("mesh.ply", o3d.io.read_triangle_mesh),
    ):
        geometry = reader(str(output / filename))
        np.testing.assert_allclose(
            (geometry.get_min_bound() + geometry.get_max_bound()) / 2,
            shift,
            rtol=0,
            atol=0.1,
        )
        np.testing.assert_allclose(
            geometry.get_max_bound() - geometry.get_min_bound(),
            [2, 2, 2],
            rtol=0,
            atol=0.15,
        )
    # Global coordinates converted directly to float32 lose centimetre detail.
    # This exercises the actual distance calculation after local recentering.
    for direction in ("point_to_mesh", "mesh_to_cloud"):
        assert report["quality"][direction]["p95"] < 0.08


def test_extreme_outlier_does_not_corrupt_reconstruction_precision(
    tmp_path: Path, sphere_path: Path
) -> None:
    sphere = np.asarray(o3d.io.read_point_cloud(str(sphere_path)).points)
    source = tmp_path / "extreme-outlier.ply"
    write_ascii_ply(source, np.vstack((sphere, [[1e9, 1e9, 1e9]])))
    output = tmp_path / "extreme-result"

    report = run_pipeline(source, output, PipelineConfig(max_planes=0))

    assert report["counts"]["input_points"] == len(sphere) + 1
    assert report["counts"]["removed_outliers"] >= 1
    for filename, reader, attribute in (
        ("cleaned.ply", o3d.io.read_point_cloud, "points"),
        ("mesh.ply", o3d.io.read_triangle_mesh, "vertices"),
    ):
        geometry = reader(str(output / filename))
        coordinates = np.asarray(getattr(geometry, attribute))
        assert len(coordinates) > 1_000
        assert np.linalg.norm(coordinates, axis=1).max() < 1.2
    # A bounding-box center chosen before cleaning would move the valid sphere
    # by hundreds of millions of units and erase its detail in float32 raycasts.
    for direction in ("point_to_mesh", "mesh_to_cloud"):
        assert report["quality"][direction]["p95"] < 0.08


@pytest.mark.parametrize("corruption", ["truncated", "nonnumeric"])
def test_rejects_malformed_ply_without_publishing_results(
    tmp_path: Path, sphere_path: Path, corruption: str
) -> None:
    lines = sphere_path.read_text().splitlines(keepends=True)
    if corruption == "truncated":
        # Keep the declared vertex count unchanged: a permissive importer may
        # otherwise return the expected shape with one silently zeroed row.
        lines.pop()
    else:
        lines[-1] = "not-a-number 0 0\n"
    source = tmp_path / f"{corruption}.ply"
    source.write_text("".join(lines))
    output = tmp_path / f"{corruption}-result"

    with pytest.raises(ValueError):
        run_pipeline(source, output, PipelineConfig(max_planes=0))

    assert not output.exists()


def test_mixed_density_reconstruction_preserves_a_thin_pipe(tmp_path: Path) -> None:
    rng = np.random.default_rng(29)
    floor_axis = np.linspace(0, 5, 70)
    x, y = np.meshgrid(floor_axis, floor_axis)
    floor = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
    theta, height = np.meshgrid(
        np.linspace(0, 2 * np.pi, 36, endpoint=False), np.linspace(0.5, 2.5, 60)
    )
    pipe = np.column_stack(
        (
            2 + 0.06 * np.cos(theta.ravel()),
            2 + 0.06 * np.sin(theta.ravel()),
            height.ravel(),
        )
    )
    points = np.vstack((floor, pipe))
    points += rng.normal(0, 0.00015, points.shape)
    source = tmp_path / "floor-and-thin-pipe.ply"
    write_ascii_ply(source, points)
    output = tmp_path / "pipe-result"

    run_pipeline(source, output, PipelineConfig(max_planes=0))

    mesh = o3d.io.read_triangle_mesh(str(output / "mesh.ply"))
    scene = o3d.t.geometry.RaycastingScene()
    scene.add_triangles(o3d.t.geometry.TriangleMesh.from_legacy(mesh))
    distances = scene.compute_distance(
        o3d.core.Tensor(pipe.astype(np.float32))
    ).numpy()
    # A globally selected BPA radius based on the sparse floor can exceed the
    # pipe radius and miss most of it despite a plausible-looking floor mesh.
    assert np.mean(distances < 0.01) >= 0.95


def test_documented_industrial_demo_preserves_observed_surfaces(tmp_path: Path) -> None:
    source = tmp_path / "industrial-demo.ply"
    metadata = generate_demo(source)

    report = run_pipeline(
        source,
        tmp_path / "industrial-demo-result",
        PipelineConfig(voxel_size=0.025, plane_distance=0.015),
    )

    assert report["counts"]["input_points"] == metadata["points"]
    assert report["quality"]["original_to_mesh"]["p95"] < 0.02
    assert report["quality"]["point_to_mesh"]["p95"] < 0.02
    assert report["quality"]["mesh_to_cloud"]["p95"] < 0.08


def test_e57_applies_scan_pose_before_world_space_crop_and_plane_fit(
    tmp_path: Path,
) -> None:
    rng = np.random.default_rng(17)
    axis = np.linspace(-0.5, 0.5, 31)
    x, y = np.meshgrid(axis, axis)
    local_points = np.column_stack(
        (x.ravel(), y.ravel(), 0.2 + rng.normal(0, 0.0005, x.size))
    )
    source = tmp_path / "posed-wall.e57"
    shift = np.array([450_000.0, 5_800_000.0, 120.0])
    half_turn = np.sqrt(0.5)
    with pye57.E57(str(source), mode="w") as scan:
        scan.write_scan_raw(
            {
                "cartesianX": local_points[:, 0],
                "cartesianY": local_points[:, 1],
                "cartesianZ": local_points[:, 2],
            },
            rotation=np.array([half_turn, 0, half_turn, 0]),
            translation=shift,
        )
    crop = (
        shift[0] + 0.1,
        shift[1] - 0.31,
        shift[2] - 0.31,
        shift[0] + 0.3,
        shift[1] + 0.31,
        shift[2] + 0.31,
    )
    output = tmp_path / "e57-result"

    report = run_pipeline(
        source,
        output,
        PipelineConfig(crop=crop, max_planes=1, plane_distance=0.005, ball_radius=0.06),
    )

    assert report["counts"]["input_points"] == len(local_points)
    assert 300 <= report["counts"]["cropped_points"] < len(local_points)
    assert len(report["planes"]) == 1
    plane = report["planes"][0]
    assert abs(plane["normal"][0]) > 0.999
    # Compare n·p+d directly: small angular errors have large effects on d at
    # site coordinates, while the geometric plane should still pass this point.
    expected_center = shift + [0.2, 0, 0]
    assert abs(np.dot(plane["normal"], expected_center) + plane["offset"]) < 0.002
    cleaned = o3d.io.read_point_cloud(str(output / "cleaned.ply"))
    assert np.all(cleaned.get_min_bound() >= np.array(crop[:3]) - 1e-6)
    assert np.all(cleaned.get_max_bound() <= np.array(crop[3:]) + 1e-6)
    assert report["quality"]["point_to_mesh"]["p95"] < 0.02


def create_staged_results(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    staged = tmp_path / ".scan2mesh-staging" / "result"
    staged.mkdir(parents=True)
    contents = {
        "mesh.ply": b"complete mesh\n",
        "cleaned.ply": b"complete cleaned cloud\n",
        "segments.ply": b"complete segmented cloud\n",
        "report.json": b'{"complete": true}\n',
    }
    for filename, payload in contents.items():
        (staged / filename).write_bytes(payload)
    return staged, contents


def windows_lock_error(code: int = 5) -> PermissionError:
    error = PermissionError(13, "Simulated Windows publication lock")
    error.winerror = code
    return error


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_publication_retries_transient_windows_locks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, winerror: int
) -> None:
    staged, contents = create_staged_results(tmp_path)
    output = tmp_path / "published"
    actual_rename = Path.rename
    attempts, waits = [], []

    def temporarily_locked(path, destination):
        if path == staged:
            attempts.append(destination)
            if len(attempts) <= 2:
                raise windows_lock_error(winerror)
        return actual_rename(path, destination)

    monkeypatch.setattr(Path, "rename", temporarily_locked)
    monkeypatch.setattr(pipeline.time, "sleep", waits.append)

    pipeline._publish_staged_results(staged, output)

    assert len(attempts) == 3
    assert len(waits) == 2
    assert all(0 < duration <= 1 for duration in waits)
    assert not staged.exists()
    assert {path.name: path.read_bytes() for path in output.iterdir()} == contents


def test_permanent_publication_lock_keeps_complete_staged_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged, contents = create_staged_results(tmp_path)
    output = tmp_path / "published"
    attempts, waits = [], []

    def permanently_locked(path, destination):
        attempts.append(destination)
        raise windows_lock_error()

    monkeypatch.setattr(Path, "rename", permanently_locked)
    monkeypatch.setattr(pipeline.time, "sleep", waits.append)

    with pytest.raises(OSError) as error:
        pipeline._publish_staged_results(staged, output)

    assert len(attempts) == 4
    assert len(waits) == 3
    assert str(staged.resolve()) in str(error.value)
    assert not output.exists()
    assert {path.name: path.read_bytes() for path in staged.iterdir()} == contents


def test_publication_never_overwrites_a_nonempty_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staged, contents = create_staged_results(tmp_path)
    output = tmp_path / "published"
    output.mkdir()
    marker = output / "existing-mesh.ply"
    marker.write_bytes(b"existing work\n")
    monkeypatch.setattr(pipeline.time, "sleep", lambda duration: pytest.fail("Do not retry existing results"))

    with pytest.raises(OSError):
        pipeline._publish_staged_results(staged, output)

    assert {path.name: path.read_bytes() for path in output.iterdir()} == {
        "existing-mesh.ply": b"existing work\n"
    }
    assert {path.name: path.read_bytes() for path in staged.iterdir()} == contents


def test_pipeline_publication_failure_preserves_real_recoverable_results(
    tmp_path: Path, sphere_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "locked-result"
    actual_rename = Path.rename
    recovery_locations = []

    def deny_final_publication(path, destination):
        if Path(destination) == output:
            recovery_locations.append(path)
            raise windows_lock_error()
        return actual_rename(path, destination)

    monkeypatch.setattr(Path, "rename", deny_final_publication)
    monkeypatch.setattr(pipeline.time, "sleep", lambda duration: None)

    with pytest.raises(OSError) as error:
        run_pipeline(sphere_path, output, PipelineConfig(max_planes=0))

    assert len(set(recovery_locations)) == 1
    recovered = recovery_locations[0]
    assert str(recovered.resolve()) in str(error.value)
    assert not output.exists()
    assert {path.name for path in recovered.iterdir()} == {
        "mesh.ply", "cleaned.ply", "segments.ply", "report.json"
    }
    report = json.loads((recovered / "report.json").read_text())
    mesh = o3d.io.read_triangle_mesh(str(recovered / "mesh.ply"))
    cleaned = o3d.io.read_point_cloud(str(recovered / "cleaned.ply"))
    segmented = o3d.io.read_point_cloud(str(recovered / "segments.ply"))
    assert len(mesh.triangles) == report["counts"]["mesh_triangles"] > 2_000
    assert len(cleaned.points) == len(segmented.points) == report["counts"]["cleaned_points"]
    assert report["input_path"] == str(sphere_path.resolve())


@pytest.mark.parametrize("surface_mode", ["global", "segmented"])
def test_progress_reports_real_stages_without_changing_results_or_printing(
    tmp_path: Path, sphere_path: Path, capfd, surface_mode: str
) -> None:
    output = tmp_path / "with-progress"
    events = []

    def observe(message: str) -> None:
        assert isinstance(message, str) and message
        files = {path.name for path in output.iterdir()} if output.exists() else set()
        events.append((message, output.exists(), files))

    config = PipelineConfig(max_planes=0, surface_mode=surface_mode)
    observed_report = run_pipeline(sphere_path, output, config, progress=observe)

    required_files = {"mesh.ply", "cleaned.ply", "segments.ply", "report.json"}
    if surface_mode == "segmented":
        required_files.add("segmentation.npz")
    position = -1
    for prefix in (
        "Laden:", "Rekonstruktion:", "Qualitaetspruefung:",
        "Ergebnisse schreiben:", "Veroeffentlichen:", "Fertig:",
    ):
        matches = [
            index for index, (message, _, _) in enumerate(events)
            if index > position and message.startswith(prefix)
        ]
        assert matches, f"Missing or unordered progress stage {prefix}"
        position = matches[0]
    assert position == len(events) - 1
    assert all(not exists for _, exists, _ in events[:-1])
    assert events[-1][1] is True
    assert events[-1][2] == required_files
    assert json.loads((output / "report.json").read_text()) == observed_report
    # A callback receives data; it must not cause the library to print by itself.
    assert capfd.readouterr().out == ""

    silent_report = run_pipeline(sphere_path, tmp_path / "without-progress", config)

    assert capfd.readouterr().out == ""
    assert silent_report == observed_report
