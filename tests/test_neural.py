"""The NKSR process boundary is testable without NKSR, CUDA or model weights.

The fake modules below verify protocol/API behavior only. They are not a
reconstruction-quality test or evidence of inference on an actual GPU.
"""

import io
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from scan2mesh import neural


POINTS = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=float)
NORMALS = np.array([[0, 0, 2], [2, 0, 0], [0, 3, 0], [0, 0, 4]], dtype=float)
FACES = np.array([[0, 2, 1], [0, 1, 3], [1, 2, 3], [2, 0, 3]], dtype=np.int64)


def archive(**values):
    result = io.BytesIO()
    np.savez(result, **values)
    return result.getvalue()


@pytest.fixture
def fake_runtime(tmp_path, monkeypatch):
    """Use real child processes with explicitly fake torch and NKSR modules."""
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "torch.py").write_text('''
import os
import numpy as np
from types import SimpleNamespace
__version__ = "test-double"
version = SimpleNamespace(cuda="test-double")
class Tensor:
    def __init__(self, array): self.array = np.asarray(array)
    def to(self, device): return self
    def detach(self): return self
    def cpu(self): return self
    def numpy(self): return self.array
def from_numpy(array): return Tensor(array)
def device(value):
    assert value == "cuda:0"
    return value
class cuda:
    @staticmethod
    def is_available(): return os.environ.get("FAKE_NO_CUDA") != "1"
    @staticmethod
    def get_device_properties(index):
        assert index == 0
        return SimpleNamespace(name="Test GPU", total_memory=8 * 1024**3)
''', encoding="utf-8")
    (runtime / "nksr.py").write_text('''
import os
import numpy as np
from types import SimpleNamespace
from torch import Tensor
__version__ = "test-double"
os.write(1, b"native import log\\n")
print("Python import log", flush=True)
class Reconstructor:
    def __init__(self, device, config):
        assert not os.environ.get("FAKE_FORBID_INIT"), "Diagnostics loaded model weights"
        assert device == "cuda:0" and config == "ks"
    def reconstruct(self, xyz, normal, **settings):
        os.write(1, b"native inference log\\n")
        assert np.allclose(np.linalg.norm(normal.array, axis=1), 1)
        if os.environ.get("FAKE_OOM"):
            raise RuntimeError("CUDA out of memory")
        if os.environ.get("FAKE_EXPECT_VOXEL"):
            assert settings == {"voxel_size": 0.01}
        else:
            assert settings == {"detail_level": 0.25}
        class Field:
            def extract_dual_mesh(self, mise_iter):
                assert mise_iter == 1
                os.write(1, b"native meshing log\\n")
                return SimpleNamespace(
                    v=Tensor(xyz.array),
                    f=Tensor(np.array([[0,2,1], [0,1,3], [1,2,3], [2,0,3]], dtype=np.int64)),
                )
        return Field()
''', encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(runtime))
    monkeypatch.delenv("SCAN2MESH_NKSR_PYTHON", raising=False)
    monkeypatch.delenv("SCAN2MESH_NKSR_WSL_DISTRO", raising=False)
    return runtime


def test_worker_roundtrip_normalizes_normals_and_keeps_native_logs_out_of_npz(fake_runtime):
    original = NORMALS.copy()
    vertices, faces, metadata = neural.reconstruct_nksr(
        POINTS, NORMALS, python=sys.executable, detail_level=0.25,
    )

    np.testing.assert_array_equal(vertices, POINTS)
    np.testing.assert_array_equal(faces, FACES)
    np.testing.assert_array_equal(NORMALS, original)
    assert metadata["gpu_name"] == "Test GPU"
    assert metadata["gpu_memory_bytes"] == 8 * 1024**3
    assert metadata["detail_level"] == 0.25
    assert metadata["inference_completed"] is True


def test_diagnostics_do_not_instantiate_model_or_download_weights(fake_runtime, monkeypatch):
    monkeypatch.setenv("FAKE_FORBID_INIT", "1")
    report = neural.diagnose_nksr(python=sys.executable)

    assert report["ready"] is True
    assert report["nksr_version"] == "test-double"
    assert "inference_completed" not in report


def test_missing_cuda_is_actionable_and_never_initializes_model(fake_runtime, monkeypatch):
    monkeypatch.setenv("FAKE_NO_CUDA", "1")
    monkeypatch.setenv("FAKE_FORBID_INIT", "1")
    report = neural.diagnose_nksr(python=sys.executable)
    assert report["ready"] is False
    assert any("CUDA is unavailable" in error for error in report["errors"])

    with pytest.raises(RuntimeError, match="CUDA is unavailable"):
        neural.reconstruct_nksr(POINTS, NORMALS, python=sys.executable)


def test_missing_dependency_is_reported_without_model_download(fake_runtime):
    (fake_runtime / "nksr.py").write_text("raise ImportError('test: extension missing')\n")
    report = neural.diagnose_nksr(python=sys.executable)
    assert report["ready"] is False
    assert any("extension missing" in error for error in report["errors"])


def test_voxel_size_overrides_detail_level(fake_runtime, monkeypatch):
    monkeypatch.setenv("FAKE_EXPECT_VOXEL", "1")
    _, _, metadata = neural.reconstruct_nksr(
        POINTS, NORMALS, python=sys.executable, detail_level=0.75, voxel_size=0.01,
    )
    assert metadata["voxel_size"] == 0.01
    assert metadata["detail_level"] is None


def test_oom_suggests_smaller_excerpt_and_does_not_return_an_alternate_mesh(fake_runtime, monkeypatch):
    monkeypatch.setenv("FAKE_OOM", "1")
    with pytest.raises(RuntimeError, match="smaller scan excerpt"):
        neural.reconstruct_nksr(POINTS, NORMALS, python=sys.executable, detail_level=0.25)


@pytest.mark.parametrize("points,normals", [
    (POINTS[:, :2], NORMALS),
    (POINTS, NORMALS[:3]),
    (POINTS * np.nan, NORMALS),
    (POINTS, np.zeros_like(NORMALS)),
    (POINTS.astype(object), NORMALS),
])
def test_bad_input_is_rejected_before_starting_a_worker(monkeypatch, points, normals):
    monkeypatch.setattr(neural.subprocess, "run", lambda *a, **kw: pytest.fail("Do not start invalid requests"))
    with pytest.raises(ValueError):
        neural.reconstruct_nksr(points, normals)


@pytest.mark.parametrize("options", [
    {"detail_level": float("nan")}, {"detail_level": 1.01},
    {"voxel_size": 0}, {"voxel_size": float("inf")}, {"timeout": 0},
])
def test_bad_settings_are_rejected_before_starting_a_worker(monkeypatch, options):
    monkeypatch.setattr(neural.subprocess, "run", lambda *a, **kw: pytest.fail("Do not start invalid requests"))
    with pytest.raises(ValueError):
        neural.reconstruct_nksr(POINTS, NORMALS, **options)


@pytest.mark.parametrize("vertices,faces", [
    (POINTS, FACES.astype(float)),
    (POINTS, np.array([[0, 1, 9]])),
    (POINTS, np.array([[0, 1, -1]])),
    (POINTS, np.array([[0, 1, 1]])),
    (np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]]), np.array([[0, 1, 2]])),
    (POINTS * np.nan, FACES),
    (POINTS, np.empty((0, 3), dtype=int)),
])
def test_invalid_worker_meshes_are_rejected(monkeypatch, vertices, faces):
    response = archive(vertices=vertices, triangles=faces, metadata=np.asarray("{}"))
    monkeypatch.setattr(neural.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, response, b""))
    with pytest.raises(RuntimeError, match="Invalid NKSR mesh"):
        neural.reconstruct_nksr(POINTS, NORMALS)


@pytest.mark.parametrize("response", [
    b"log text instead of an archive",
    archive(metadata=np.asarray("{}")),
    archive(vertices=POINTS, triangles=FACES, metadata=np.asarray({"code": "must not be unpickled"}, dtype=object)),
])
def test_invalid_or_pickle_payloads_are_rejected(monkeypatch, response):
    monkeypatch.setattr(neural.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, response, b"worker log"))
    with pytest.raises(RuntimeError, match="invalid result archive"):
        neural.reconstruct_nksr(POINTS, NORMALS)


def test_wsl_paths_are_argv_values_and_source_is_sent_without_shared_paths(monkeypatch):
    calls = []
    monkeypatch.setenv("SCAN2MESH_NKSR_PYTHON", "/opt/NKSR env/bin/python")
    monkeypatch.setenv("SCAN2MESH_NKSR_WSL_DISTRO", "Ubuntu Ä & $(not-a-command)")
    def run(command, **options):
        calls.append((command, options))
        return subprocess.CompletedProcess(command, 0, archive(metadata=np.asarray('{"ready": true}')), b"")
    monkeypatch.setattr(neural.subprocess, "run", run)

    assert neural.diagnose_nksr()["ready"] is True
    command, options = calls[0]
    assert command[:6] == ["wsl.exe", "--distribution", "Ubuntu Ä & $(not-a-command)", "--exec", "/opt/NKSR env/bin/python", "-u"]
    assert command[6] == "-c"
    assert "def main():" in command[7]
    assert command[-1] == "--diagnose"
    assert not options.get("shell", False)
    assert options["input"] == b""


def test_missing_interpreter_and_timeout_have_actionable_errors(monkeypatch):
    def missing(command, **options):
        raise FileNotFoundError("test interpreter missing")
    monkeypatch.setattr(neural.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="nksr-python"):
        neural.diagnose_nksr(python="missing-python")

    def timeout(command, **options):
        raise subprocess.TimeoutExpired(command, options["timeout"])
    monkeypatch.setattr(neural.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="exceeded 0.1 seconds"):
        neural.reconstruct_nksr(POINTS, NORMALS, timeout=0.1)

    with pytest.raises(RuntimeError, match="Linux worker has stopped"):
        neural.reconstruct_nksr(POINTS, NORMALS, timeout=0.1, wsl_distro="Ubuntu")
