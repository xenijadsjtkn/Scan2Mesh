"""Check the standalone export contract with a fake NKSR, without GPU inference."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import open3d as o3d
import pytest


SPEC = importlib.util.spec_from_file_location(
    "nksr_direct", Path(__file__).parents[1] / "scripts" / "nksr_direct.py"
)
direct = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(direct)


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
            assert detail_level == 0.0
            calls.update(points=xyz.array.copy(), normals=normal.array.copy())

            class Field:
                def extract_dual_mesh(self, *, mise_iter):
                    assert mise_iter == 1
                    return SimpleNamespace(v=Tensor(xyz.array), f=Tensor(faces))

            return Field()

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        device=lambda value: value, as_tensor=tensor, float32=np.float32,
        cuda=SimpleNamespace(get_device_name=lambda index: "test GPU"),
    ))
    monkeypatch.setitem(sys.modules, "nksr", SimpleNamespace(Reconstructor=Reconstructor))
    return calls, faces


@pytest.mark.parametrize("units,scale", [("m", 1.0), ("mm", 1000.0)])
@pytest.mark.parametrize("colored", [True, False])
def test_direct_preserves_points_faces_normals_units_and_transfers_colors(
    tmp_path, fake_backend, units, scale, colored,
):
    calls, faces = fake_backend
    points = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.], [0., 0., 1.]])
    origin = np.array([450_000.0, 5_800_000.0, 120.0])
    world = (points + origin) * scale
    normals = np.array([[0., 0., 2.], [2., 0., 0.], [0., -3., 0.], [0., 0., 4.]])
    colors = np.array([[1., 0., 0.], [0., 1., 0.], [0., 0., 1.], [1., 1., 1.]])
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
