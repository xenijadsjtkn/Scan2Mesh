"""Check the standalone export contract with a fake NKSR, without GPU inference."""

import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import open3d as o3d
import pytest


from scan2mesh import nksr_direct as direct


class Tensor:
    def __init__(self, array):
        self.array = np.asarray(array)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.array


@pytest.fixture
def fake_backend(monkeypatch):
    calls = {}
    faces = np.array([[0, 1, 2], [0, 0, 1]], dtype=np.int32)

    def tensor(array, *, dtype, device):
        assert device == "cuda:0"
        return Tensor(np.asarray(array, dtype=dtype))

    class Reconstructor:
        def __init__(self, device, config):
            assert device == "cuda:0" and config == "ks"

        def reconstruct(self, xyz, normal, *, detail_level):
            calls.update(points=xyz.array.copy(), normals=normal.array.copy())
            calls.setdefault("reconstruction_calls", []).append(detail_level)

            class Field:
                def extract_dual_mesh(self, *, mise_iter, trim):
                    assert mise_iter == 1
                    calls.setdefault("extraction_calls", []).append(trim)
                    if not trim and calls.get("fail_untrimmed"):
                        raise RuntimeError("test: untrimmed extraction failed")
                    output_faces = faces if trim else np.vstack((faces, [0, 2, 3]))
                    return SimpleNamespace(v=Tensor(xyz.array), f=Tensor(output_faces))

            return Field()

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        device=lambda value: value, as_tensor=tensor, float32=np.float32,
        cuda=SimpleNamespace(is_available=lambda: True, get_device_name=lambda index: "test GPU"),
    ))
    monkeypatch.setitem(sys.modules, "nksr", SimpleNamespace(Reconstructor=Reconstructor))
    return calls, faces


@pytest.mark.parametrize("units,scale", [("m", 1.0), ("mm", 1000.0)])
@pytest.mark.parametrize("colored", [True, False])
def test_direct_preserves_points_faces_normals_units_and_transfers_colors(
    tmp_path, fake_backend, units, scale, colored,
):
    calls, faces = fake_backend
    # Keep a duplicate and a distant point, including unused mesh vertices.
    points = np.array([
        [0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.],
        [0., 0., 0.], [100., 100., 100.],
    ])
    origin = np.array([450_000.0, 5_800_000.0, 120.0])
    world = (points + origin) * scale
    normals = np.array([
        [0., 0., 2.], [2., 0., 0.], [0., -3., 0.], [0., 0., 4.],
        [0., 0., 2.], [1., 0., 0.],
    ])
    colors = np.array([
        [1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [1., 1., 1.],
        [1., 0., 0.], [1., 0., 1.],
    ])
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(world))
    cloud.normals = o3d.utility.Vector3dVector(normals)
    if colored:
        cloud.colors = o3d.utility.Vector3dVector(colors)
    source = tmp_path / "scan with spaces and \u00e4.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)
    source_bytes = source.read_bytes()

    output_path = direct.main(["--input", str(source), "--output-root", str(tmp_path / "runs"), "--units", units])

    expected_local = (world - np.median(world, axis=0)) / scale
    np.testing.assert_array_equal(calls["points"], expected_local.astype(np.float32))
    np.testing.assert_array_equal(calls["normals"], normals.astype(np.float32))
    with np.load(output_path.parent / "nksr_raw.npz", allow_pickle=False) as raw:
        np.testing.assert_array_equal(raw["vertices"], calls["points"])
        np.testing.assert_array_equal(raw["triangles"], faces)
        np.testing.assert_array_equal(raw["coordinate_origin"], np.median(world, axis=0))
        assert raw["input_units"].item() == units
    loaded = o3d.io.read_triangle_mesh(str(output_path))
    np.testing.assert_array_equal(np.asarray(loaded.vertices), world)
    # The repeated-index triangle must survive: this path has no mesh cleanup.
    np.testing.assert_array_equal(np.asarray(loaded.triangles), faces)
    assert source.read_bytes() == source_bytes
    assert loaded.has_vertex_colors() == colored
    if colored:
        np.testing.assert_array_equal(np.asarray(loaded.vertex_colors), colors)
        assert output_path.name == "mesh_colored.ply"
    else:
        assert output_path.name == "mesh_raw.ply"
    info = json.loads((output_path.parent / "run.json").read_text())
    assert info["input_points"] == len(points)
    assert info["normal_source"] == "provided"
    assert info["triangles"] == len(faces)
    assert info["detail_level"] == 1.0
    assert calls["reconstruction_calls"] == [1.0]
    assert calls["extraction_calls"] == [True, False]
    assert info["trim"] is True
    assert info["compare_trim"] is True
    assert info["exports"] == [{
        "trim": True, "vertices": len(points), "triangles": len(faces),
        "mesh_path": str(output_path), "raw_path": str(output_path.parent / "nksr_raw.npz"),
    }, {
        "trim": False, "vertices": len(points), "triangles": len(faces) + 1,
        "mesh_path": str(output_path.parent / ("mesh_colored_untrimmed.ply" if colored else "mesh_raw_untrimmed.ply")),
        "raw_path": str(output_path.parent / "nksr_raw_untrimmed.npz"),
    }]


@pytest.mark.parametrize("units,scale", [("m", 1.0), ("mm", 1000.0)])
@pytest.mark.parametrize("colored", [True, False])
def test_trim_comparison_uses_one_field_and_exports_both_raw_meshes(
    tmp_path, fake_backend, units, scale, colored,
):
    calls, trimmed_faces = fake_backend
    world = (np.eye(4, 3) + [450_000.0, 5_800_000.0, 120.0]) * scale
    normals = np.array([[0., 0., 2.], [2., 0., 0.], [0., -3., 0.], [0., 0., 4.]])
    colors = np.array([[1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [1., 1., 1.]])
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(world))
    cloud.normals = o3d.utility.Vector3dVector(normals)
    if colored:
        cloud.colors = o3d.utility.Vector3dVector(colors)
    source = tmp_path / "comparison.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)
    source_bytes = source.read_bytes()

    primary = direct.main([
        "--input", str(source), "--output-root", str(tmp_path / "runs"),
        "--units", units, "--detail-level", "0.5", "--compare-trim",
    ])

    assert calls["reconstruction_calls"] == [0.5]
    assert calls["extraction_calls"] == [True, False]
    np.testing.assert_array_equal(calls["normals"], normals.astype(np.float32))
    info = json.loads((primary.parent / "run.json").read_text())
    assert info["detail_level"] == 0.5
    assert info["compare_trim"] is True
    assert info["mesh_path"] == str(primary)
    assert [entry["trim"] for entry in info["exports"]] == [True, False]
    assert [entry["triangles"] for entry in info["exports"]] == [2, 3]
    untrimmed_faces = np.vstack((trimmed_faces, [0, 2, 3]))
    for entry, expected_faces, suffix in zip(
        info["exports"], (trimmed_faces, untrimmed_faces), ("", "_untrimmed")
    ):
        mesh_path = Path(entry["mesh_path"])
        expected_stem = "mesh_colored" if colored else "mesh_raw"
        assert mesh_path.name == f"{expected_stem}{suffix}.ply"
        with np.load(entry["raw_path"], allow_pickle=False) as raw:
            np.testing.assert_array_equal(raw["vertices"], calls["points"])
            np.testing.assert_array_equal(raw["triangles"], expected_faces)
            assert raw["trim"].item() == entry["trim"]
            assert raw["detail_level"].item() == 0.5
        mesh = o3d.io.read_triangle_mesh(str(mesh_path))
        np.testing.assert_array_equal(np.asarray(mesh.vertices), world)
        np.testing.assert_array_equal(np.asarray(mesh.triangles), expected_faces)
        assert mesh.has_vertex_colors() == colored
        if colored:
            np.testing.assert_array_equal(np.asarray(mesh.vertex_colors), colors)
    assert source.read_bytes() == source_bytes


def test_primary_mesh_and_metadata_survive_untrimmed_extraction_failure(tmp_path, fake_backend):
    calls, faces = fake_backend
    calls["fail_untrimmed"] = True
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.eye(4, 3)))
    cloud.normals = o3d.utility.Vector3dVector(np.ones((4, 3)))
    source = tmp_path / "scan.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)

    with pytest.raises(RuntimeError, match="untrimmed extraction failed"):
        direct.run(source, tmp_path / "runs", compare_trim=True)

    primary_paths = list((tmp_path / "runs").rglob("mesh_raw.ply"))
    assert len(primary_paths) == 1
    np.testing.assert_array_equal(
        np.asarray(o3d.io.read_triangle_mesh(str(primary_paths[0])).triangles), faces
    )
    info = json.loads((primary_paths[0].parent / "run.json").read_text())
    assert info["compare_trim"] is True
    assert len(info["exports"]) == 1
    assert info["exports"][0]["trim"] is True
    assert Path(info["exports"][0]["raw_path"]).is_file()
    assert calls["reconstruction_calls"] == [1.0]
    assert calls["extraction_calls"] == [True, False]


def test_primary_report_survives_partial_write_of_second_report(tmp_path, fake_backend, monkeypatch):
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.eye(4, 3)))
    cloud.normals = o3d.utility.Vector3dVector(np.ones((4, 3)))
    source = tmp_path / "scan.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)
    original_write = Path.write_text
    report_writes = 0

    def partial_write(path, text, *args, **kwargs):
        nonlocal report_writes
        if path.name == "run.json.tmp":
            report_writes += 1
            if report_writes == 2:
                original_write(path, text[:10], *args, **kwargs)
                raise OSError("test: second report write failed")
        return original_write(path, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", partial_write)
    with pytest.raises(OSError, match="second report write failed"):
        direct.run(source, tmp_path / "runs", compare_trim=True)

    reports = list((tmp_path / "runs").rglob("run.json"))
    assert len(reports) == 1
    info = json.loads(reports[0].read_text())
    assert len(info["exports"]) == 1
    assert info["exports"][0]["trim"] is True
    assert Path(info["mesh_path"]).is_file()
    assert Path(info["raw_path"]).is_file()
    assert (reports[0].parent / "mesh_raw_untrimmed.ply").is_file()
    assert (reports[0].parent / "nksr_raw_untrimmed.npz").is_file()


@pytest.mark.parametrize("detail", ["-0.1", "1.1", "nan", "inf", "invalid"])
def test_cli_rejects_invalid_detail_before_reading_input(tmp_path, detail):
    with pytest.raises(SystemExit) as error:
        direct.main([
            "--input", str(tmp_path / "missing.ply"), "--output-root", str(tmp_path / "runs"),
            "--detail-level", detail,
        ])
    assert error.value.code == 2
    assert not (tmp_path / "runs").exists()


def test_direct_propagates_native_nksr_error_without_fallback(tmp_path, fake_backend, monkeypatch):
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.eye(3)))
    cloud.normals = o3d.utility.Vector3dVector(np.eye(3))
    source = tmp_path / "scan.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)

    class BrokenReconstructor:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("test: native NKSR failure")

    monkeypatch.setitem(sys.modules, "nksr", SimpleNamespace(Reconstructor=BrokenReconstructor))
    with pytest.raises(RuntimeError, match="native NKSR failure"):
        direct.run(source, tmp_path / "runs")
    assert not list((tmp_path / "runs").rglob("*.ply"))


def test_raw_mesh_survives_color_transfer_failure(tmp_path, fake_backend, monkeypatch):
    import scipy.spatial

    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.eye(3)))
    cloud.normals = o3d.utility.Vector3dVector(np.eye(3))
    cloud.colors = o3d.utility.Vector3dVector(np.eye(3))
    source = tmp_path / "scan.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)

    def broken_tree(*args, **kwargs):
        raise RuntimeError("test: color transfer failed")

    monkeypatch.setattr(scipy.spatial, "cKDTree", broken_tree)
    with pytest.raises(RuntimeError, match="color transfer failed"):
        direct.run(source, tmp_path / "runs")
    raw_paths = list((tmp_path / "runs").rglob("nksr_raw.npz"))
    assert len(raw_paths) == 1
    with np.load(raw_paths[0], allow_pickle=False) as raw:
        np.testing.assert_array_equal(raw["triangles"], fake_backend[1])


def test_missing_normals_use_original_default_estimation_and_orientation(
    tmp_path, fake_backend, monkeypatch,
):
    calls, _ = fake_backend
    points = np.random.default_rng(41).normal(size=(64, 3))
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    normal_calls = []

    class TrackedCloud:
        def __getattr__(self, name):
            return getattr(cloud, name)

        def estimate_normals(self, *args, **kwargs):
            normal_calls.append(("estimate", args, kwargs))
            cloud.estimate_normals(*args, **kwargs)

        def orient_normals_consistent_tangent_plane(self, *args, **kwargs):
            normal_calls.append(("orient", args, kwargs))
            cloud.orient_normals_consistent_tangent_plane(*args, **kwargs)

    source = tmp_path / "missing-normals.pts"
    source.touch()
    monkeypatch.setattr(o3d.io, "read_point_cloud", lambda path: TrackedCloud())

    primary = direct.run(source, tmp_path / "runs")

    assert normal_calls == [("estimate", (), {}), ("orient", (30,), {})]
    np.testing.assert_array_equal(
        calls["points"], (points - np.median(points, axis=0)).astype(np.float32)
    )
    np.testing.assert_array_equal(calls["normals"], np.asarray(cloud.normals).astype(np.float32))
    assert calls["reconstruction_calls"] == [1.0]
    assert calls["extraction_calls"] == [True, False]
    info = json.loads((primary.parent / "run.json").read_text())
    assert info["normal_source"] == "estimated"
    assert info["input_points"] == len(points)


def test_worker_result_file_written_only_after_both_exports_succeed(
    tmp_path, fake_backend,
):
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.eye(4, 3)))
    cloud.normals = o3d.utility.Vector3dVector(np.ones((4, 3)))
    source = tmp_path / "scan.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)
    result_file = tmp_path / "worker-result.json"

    primary = direct.main([
        "--input", str(source), "--output-root", str(tmp_path / "runs"),
        "--result-file", str(result_file),
    ])

    assert json.loads(result_file.read_text()) == {"mesh_path": str(primary)}
    assert fake_backend[0]["extraction_calls"] == [True, False]


def test_failed_worker_does_not_write_success_result_file(tmp_path, fake_backend):
    fake_backend[0]["fail_untrimmed"] = True
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(np.eye(4, 3)))
    cloud.normals = o3d.utility.Vector3dVector(np.ones((4, 3)))
    source = tmp_path / "scan.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)
    result_file = tmp_path / "worker-result.json"

    with pytest.raises(RuntimeError, match="untrimmed extraction failed"):
        direct.main([
            "--input", str(source), "--output-root", str(tmp_path / "runs"),
            "--result-file", str(result_file),
        ])

    assert not result_file.exists()
    assert len(list((tmp_path / "runs").rglob("run.json"))) == 1


def test_worker_rejects_e57_with_export_instruction_before_loading_backend(tmp_path):
    with pytest.raises(ValueError, match="als PLY oder PTS exportieren"):
        direct.run(tmp_path / "scan.e57", tmp_path / "runs")
    assert not (tmp_path / "runs").exists()


def test_worker_reports_cuda_unavailable_without_creating_run(tmp_path, fake_backend, monkeypatch):
    source = tmp_path / "scan.pts"
    source.touch()
    monkeypatch.setattr(sys.modules["torch"].cuda, "is_available", lambda: False)

    with pytest.raises(RuntimeError, match="cuda:0"):
        direct.run(source, tmp_path / "runs")

    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("missing_package", ["torch", "nksr"])
def test_worker_reports_missing_gpu_package_without_creating_run(
    tmp_path, fake_backend, monkeypatch, missing_package,
):
    source = tmp_path / "scan.pts"
    source.touch()
    monkeypatch.setitem(sys.modules, missing_package, None)

    with pytest.raises(RuntimeError, match="PyTorch" if missing_package == "torch" else "NKSR-Paket"):
        direct.run(source, tmp_path / "runs")

    assert not (tmp_path / "runs").exists()


def test_default_desktop_reaches_direct_reconstruction_and_keeps_both_exports(
    tmp_path, fake_backend, monkeypatch,
):
    from scan2mesh import desktop, nksr_runtime

    points = np.vstack((np.eye(3), [0., 0., 0.], [0., 0., 0.], [100., 100., 100.]))
    normals = np.tile([0., 0., 2.], (len(points), 1))
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    cloud.normals = o3d.utility.Vector3dVector(normals)
    source = tmp_path / "original points.ply"
    assert o3d.io.write_point_cloud(str(source), cloud)
    source_bytes = source.read_bytes()
    output_root = tmp_path / "runs"
    transports = []

    def transport(input_path, destination, *, units, python, wsl_distro):
        transports.append((input_path, destination, units, python, wsl_distro))
        return direct.run(input_path, destination, units=units)

    monkeypatch.setattr(desktop, "choose_scan_file", lambda: source)
    monkeypatch.setattr(desktop, "RUNS_ROOT", output_root)
    monkeypatch.setattr(nksr_runtime, "run_direct", transport)

    result = desktop.main([])

    assert transports == [(source.resolve(), output_root, "m", None, None)]
    info = json.loads((result / "run.json").read_text())
    assert info["model"] == "ks"
    assert info["detail_level"] == 1.0
    assert info["mise_iter"] == 1
    assert info["input_points"] == len(points)
    assert info["normal_source"] == "provided"
    assert info["compare_trim"] is True
    assert [entry["trim"] for entry in info["exports"]] == [True, False]
    assert all(Path(entry["mesh_path"]).is_file() for entry in info["exports"])
    assert all(Path(entry["raw_path"]).is_file() for entry in info["exports"])
    calls, _ = fake_backend
    np.testing.assert_array_equal(
        calls["points"], (points - np.median(points, axis=0)).astype(np.float32)
    )
    np.testing.assert_array_equal(calls["normals"], normals.astype(np.float32))
    assert calls["reconstruction_calls"] == [1.0]
    assert calls["extraction_calls"] == [True, False]
    assert source.read_bytes() == source_bytes
