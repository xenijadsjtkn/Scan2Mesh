"""NKSR routing and coordinate contracts, without GPU inference or model weights."""

import json
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest
from scipy.spatial import Delaunay

from scan2mesh import cli, desktop, neural, pipeline
from scan2mesh.pipeline import PipelineConfig, run_pipeline


def forbid_call(*args, **kwargs):
    pytest.fail("This path must not read a scan, reconstruct, or open a picker")


@pytest.fixture
def plane_path(tmp_path: Path) -> Path:
    x, y = np.meshgrid(np.linspace(-0.5, 0.5, 13), np.linspace(-0.5, 0.5, 13))
    points = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))
    source = tmp_path / "plane.ply"
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    assert o3d.io.write_point_cloud(str(source), cloud)
    return source


@pytest.mark.parametrize("scale", [1.0, 1000.0], ids=["metres", "millimetres"])
@pytest.mark.parametrize("backend_voxel", [None, 0.02], ids=["detail-level", "explicit-scale"])
def test_pipeline_preserves_world_coordinates_units_and_neural_report(
    plane_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    scale: float, backend_voxel: float | None,
) -> None:
    input_units = "m" if scale == 1 else "mm"
    requested_voxel = backend_voxel * scale if backend_voxel is not None else None
    world_origin = np.array([450_000.0, 5_800_000.0, 120.0]) * scale
    source_cloud = o3d.io.read_point_cloud(str(plane_path))
    source_cloud.points = o3d.utility.Vector3dVector(
        np.asarray(source_cloud.points) * scale + world_origin
    )
    assert o3d.io.write_point_cloud(str(plane_path), source_cloud)
    calls = []

    def reconstruct(points, normals, **options):
        calls.append((points.copy(), normals.copy(), options))
        triangles = Delaunay(points[:, :2]).simplices.astype(np.int32)
        return points.copy(), triangles, {"backend": "nksr", "experimental": True, "device": "test GPU"}

    monkeypatch.setattr(neural, "reconstruct_nksr", reconstruct)
    monkeypatch.setattr(pipeline, "_reconstruct", forbid_call)
    output = tmp_path / "result"
    report = run_pipeline(
        plane_path, output,
        PipelineConfig(
            reconstruction="nksr", input_units=input_units, max_planes=0, nksr_python="/env/python",
            nksr_wsl_distro="Ubuntu", nksr_detail_level=0.3,
            nksr_voxel_size=requested_voxel, nksr_timeout=120,
        ),
    )

    assert len(calls) == 1
    points, normals, options = calls[0]
    assert np.max(np.abs(points)) <= 0.501
    np.testing.assert_allclose(np.ptp(points, axis=0), [1, 1, 0], atol=1e-8)
    assert normals.shape == points.shape
    np.testing.assert_allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-7)
    assert options == {
        "python": "/env/python", "wsl_distro": "Ubuntu", "detail_level": 0.3,
        "voxel_size": backend_voxel, "timeout": 120,
    }
    np.testing.assert_allclose(
        report["analysis"]["coordinate_origin"], world_origin, rtol=0, atol=1e-8 * scale
    )
    exported = o3d.io.read_triangle_mesh(str(output / "mesh.ply"))
    np.testing.assert_allclose(
        np.asarray(exported.vertices), points * scale + world_origin, rtol=0, atol=1e-8 * scale
    )
    np.testing.assert_allclose(
        np.ptp(np.asarray(exported.vertices), axis=0), np.ptp(points, axis=0) * scale
    )
    assert report["quality"]["point_to_mesh"]["p95"] < 1e-5 * scale
    assert report["quality"]["mesh_to_cloud"]["p95"] < 0.08 * scale
    assert report["neural_reconstruction"]["backend"] == "nksr"
    assert report["neural_reconstruction"]["device"] == "test GPU"
    assert report["neural_reconstruction"]["semantic_segmentation"] is False
    assert report["neural_reconstruction"]["scanner_positions_used"] is False
    assert report["neural_reconstruction"]["input_units"] == input_units
    assert report["neural_reconstruction"]["backend_units"] == "m"
    assert report["neural_reconstruction"]["input_units_to_meters"] == 1 / scale
    assert report["neural_reconstruction"]["requested_voxel_size"] == requested_voxel
    assert report["analysis"]["ball_radii"] is None
    assert report["analysis"]["poisson_vertex_density"] is None
    assert json.loads((output / "report.json").read_text()) == report


def test_backend_failure_publishes_no_result_and_does_not_fall_back(
    plane_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_backend(*args, **kwargs):
        raise RuntimeError("NKSR GPU unavailable")

    monkeypatch.setattr(neural, "reconstruct_nksr", fail_backend)
    monkeypatch.setattr(pipeline, "_reconstruct", forbid_call)
    output = tmp_path / "runs" / "result"

    with pytest.raises(RuntimeError, match="NKSR GPU unavailable"):
        run_pipeline(plane_path, output, PipelineConfig(reconstruction="nksr", max_planes=0))

    assert not output.exists()
    assert not output.parent.exists()


@pytest.mark.parametrize("ready", [True, False])
def test_cli_neural_check_reports_readiness_without_processing(
    monkeypatch: pytest.MonkeyPatch, capsys, ready: bool
) -> None:
    calls = []
    diagnosis = {"ready": ready, "errors": [] if ready else ["CUDA unavailable"]}

    def diagnose(**options):
        calls.append(options)
        return diagnosis

    monkeypatch.setattr(neural, "diagnose_nksr", diagnose)
    monkeypatch.setattr(neural, "reconstruct_nksr", forbid_call)
    monkeypatch.setattr(pipeline, "load_cloud", forbid_call)
    monkeypatch.setattr(pipeline, "run_pipeline", forbid_call)
    arguments = ["neural-check", "--nksr-python", "/env/python", "--nksr-wsl-distro", "Ubuntu"]

    if ready:
        cli.main(arguments)
    else:
        with pytest.raises(SystemExit) as error:
            cli.main(arguments)
        assert error.value.code == 2

    assert json.loads(capsys.readouterr().out) == diagnosis
    assert calls == [{"python": "/env/python", "wsl_distro": "Ubuntu", "timeout": 30.0}]


def test_cli_process_forwards_nksr_settings_and_outputs_backend_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    calls = []

    def process(source, output, config, *, progress=None):
        calls.append((source, output, config))
        return {"counts": {"mesh_triangles": 2}, "quality": {}, "neural_reconstruction": {"backend": "nksr"}}

    monkeypatch.setattr(pipeline, "run_pipeline", process)
    source, output = tmp_path / "scan.ply", tmp_path / "output"
    cli.main([
        "process", str(source), "--output", str(output), "--reconstruction", "nksr", "--units", "mm",
        "--nksr-python", "/env/python", "--nksr-detail-level", "0.4",
        "--nksr-voxel-size", "0.02", "--nksr-timeout", "90",
    ])

    assert len(calls) == 1
    assert calls[0][:2] == (source, output)
    config = calls[0][2]
    assert config.reconstruction == "nksr"
    assert config.input_units == "mm"
    assert (config.nksr_python, config.nksr_detail_level, config.nksr_voxel_size, config.nksr_timeout) == (
        "/env/python", 0.4, 0.02, 90,
    )
    assert json.loads(capsys.readouterr().out)["neural_reconstruction"] == {"backend": "nksr"}


@pytest.mark.parametrize("ready", [True, False])
def test_desktop_neural_check_skips_picker_and_creates_no_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys, ready: bool
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(desktop, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_call)
    monkeypatch.setattr(pipeline, "run_pipeline", forbid_call)
    monkeypatch.setattr(neural, "reconstruct_nksr", forbid_call)
    calls = []

    def diagnose(**options):
        calls.append(options)
        return {"ready": ready}

    monkeypatch.setattr(neural, "diagnose_nksr", diagnose)
    if ready:
        assert desktop.main(["--check-neural"]) is None
    else:
        with pytest.raises(SystemExit) as error:
            desktop.main(["--check-neural"])
        assert error.value.code == 2

    assert json.loads(capsys.readouterr().out) == {"ready": ready}
    assert calls == [{"python": None, "wsl_distro": None, "timeout": 30.0}]
    assert not runs_root.exists()


@pytest.mark.parametrize("units, plane_distance", [("m", 0.01), ("mm", 10)])
def test_desktop_nksr_preserves_input_units_crop_and_detail_without_downsampling(
    plane_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    units: str, plane_distance: float,
) -> None:
    monkeypatch.setattr(desktop, "RUNS_ROOT", tmp_path / "runs")
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_call)
    calls = []

    def process(source, output, config, *, progress=None):
        calls.append((source, output, config))
        return {"counts": {"mesh_triangles": 2}}

    monkeypatch.setattr(pipeline, "run_pipeline", process)
    result = desktop.main([
        "--input", str(plane_path), "--reconstruction", "nksr", "--units", units,
        "--crop", "1", "2", "3", "4", "5", "6", "--normal-radius", "0.5",
        "--nksr-python", "/env/python", "--nksr-wsl-distro", "Ubuntu",
        "--nksr-detail-level", "0.2", "--nksr-voxel-size", "0.05",
    ])

    assert len(calls) == 1
    source, output, config = calls[0]
    assert source == plane_path.resolve()
    assert result == output
    assert config.reconstruction == "nksr"
    assert config.input_units == units
    assert config.voxel_size == 0
    assert config.plane_distance == plane_distance
    assert config.crop == (1, 2, 3, 4, 5, 6)
    assert config.normal_radius == 0.5
    assert (config.nksr_python, config.nksr_wsl_distro) == ("/env/python", "Ubuntu")
    assert (config.nksr_detail_level, config.nksr_voxel_size) == (0.2, 0.05)


def test_desktop_rejects_segmented_nksr_before_picker_or_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runs_root = tmp_path / "runs"
    monkeypatch.setattr(desktop, "RUNS_ROOT", runs_root)
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_call)
    monkeypatch.setattr(pipeline, "run_pipeline", forbid_call)

    with pytest.raises(SystemExit) as error:
        desktop.main(["--reconstruction", "nksr", "--surface-mode", "segmented"])

    assert error.value.code == 2
    assert not runs_root.exists()


@pytest.mark.parametrize("options", [
    {"input_units": "cm"},
    {"surface_mode": "segmented"},
    {"nksr_detail_level": float("nan")},
    {"nksr_detail_level": 1.1},
    {"nksr_voxel_size": 0},
    {"nksr_timeout": float("inf")},
    {"nksr_python": " "},
])
def test_invalid_nksr_config_is_rejected(options: dict) -> None:
    with pytest.raises(ValueError):
        PipelineConfig(reconstruction="nksr", **options)
