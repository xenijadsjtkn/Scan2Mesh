"""Exercise setup recovery and real-check contracts without installing packages."""

import importlib.util
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest


pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux installer contracts run under Linux/WSL")


ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "scripts/install_nksr.sh"
SPEC = importlib.util.spec_from_file_location("check_nksr", ROOT / "scripts/check_nksr.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


@pytest.fixture
def backend(monkeypatch):
    calls = []

    class Tensor:
        def __init__(self, array):
            self.array = np.asarray(array)

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self.array

    class Reconstructor:
        def __init__(self, device, config):
            assert device == "cuda:0" and config == "ks"
            print("test: checkpoint progress")
            os.write(1, b"test: native backend progress\n")
            import ctypes
            ctypes.CDLL(None).printf(b"test: buffered C progress\n")

        def reconstruct(self, xyz, normal, *, detail_level):
            assert xyz.array.shape == normal.array.shape == (1_200, 3)
            assert detail_level == 1.0
            calls.append("reconstruct")

            def extract(*, mise_iter, trim):
                assert mise_iter == 1
                calls.append(trim)
                faces = np.array([[0, 1, 2]], dtype=np.int32)
                if not trim and "empty" in calls:
                    faces = np.empty((0, 3), dtype=np.int32)
                return SimpleNamespace(v=xyz, f=Tensor(faces))

            return SimpleNamespace(extract_dual_mesh=extract)

    cuda = SimpleNamespace(
        is_available=lambda: True, get_device_name=lambda _: "test GPU",
        synchronize=lambda _: calls.append("synchronized"),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        __version__="2.7.0+cu128", version=SimpleNamespace(cuda="12.8"), cuda=cuda,
        device=lambda value: value, float32=np.float32,
        as_tensor=lambda array, **kwargs: Tensor(array),
    ))
    monkeypatch.setitem(sys.modules, "nksr", SimpleNamespace(__version__="1.0.3", Reconstructor=Reconstructor))
    monkeypatch.setitem(sys.modules, "open3d", SimpleNamespace(__version__="0.19.0"))
    return calls, cuda


def test_checker_requires_real_field_and_both_exports_before_ready(backend, capfd):
    assert checker.main(["--smoke"]) == 0
    output, error = capfd.readouterr()
    report = json.loads(output)
    assert report["ready"] is True and report["smoke"] is True
    assert report["python"] == sys.executable
    assert [entry["trim"] for entry in report["exports"]] == [True, False]
    assert backend[0] == ["reconstruct", True, False, "synchronized"]
    assert "checkpoint progress" in error and "native backend progress" in error
    assert "buffered C progress" in error


def test_checker_does_not_mark_cuda_unavailable_as_ready(backend, monkeypatch, capfd):
    monkeypatch.setattr(backend[1], "is_available", lambda: False)
    assert checker.main(["--smoke"]) == 1
    report = json.loads(capfd.readouterr().out)
    assert report["ready"] is False and report["stage"] == "cuda"
    assert backend[0] == []


def test_checker_rejects_empty_untrimmed_mesh(backend, capfd):
    backend[0].append("empty")
    assert checker.main(["--smoke"]) == 1
    report = json.loads(capfd.readouterr().out)
    assert report["ready"] is False and report["stage"] == "untrimmed_mesh"
    assert len(report["exports"]) == 1


def test_checker_rejects_wrong_managed_version_before_model_load(tmp_path, backend, capfd):
    manifest = tmp_path / "versions.json"
    manifest.write_text(json.dumps({
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "torch": "different", "cuda": "12.8", "open3d": "0.19.0",
    }))
    assert checker.main(["--smoke", "--manifest", str(manifest)]) == 1
    report = json.loads(capfd.readouterr().out)
    assert report["ready"] is False and "torch: erwartet" in report["error"]
    assert backend[0] == []


def test_checker_without_smoke_never_claims_readiness(capfd):
    assert checker.main([]) == 1
    report = json.loads(capfd.readouterr().out)
    assert report["ready"] is False and report["smoke"] is False


def test_installer_refuses_nonempty_unmanaged_prefix(tmp_path):
    prefix = tmp_path / "someone-elses-environment"
    prefix.mkdir()
    original = prefix / "user-file"
    original.write_text("preserve me")
    result = subprocess.run([
        "bash", "-c", 'source "$1"; PREFIX="$2"; claim_prefix', "bash", str(INSTALLER), str(prefix),
    ], capture_output=True, text=True)
    assert result.returncode != 0
    assert original.read_text() == "preserve me"
    assert list(prefix.iterdir()) == [original]


def test_failed_install_resumes_and_matching_receipt_only_rechecks_gpu(tmp_path):
    prefix = tmp_path / "managed"
    body = r'''
source "$1"
require_platform() { :; }
install_system_packages() { echo system >> "$PREFIX/events"; }
bootstrap_conda() { echo conda >> "$PREFIX/events"; }
install_environment() {
    echo environment >> "$PREFIX/events"
    mkdir -p "$ENVIRONMENT/bin"
    printf '#!/bin/sh\nexit 0\n' > "$ENVIRONMENT/bin/python"
    chmod +x "$ENVIRONMENT/bin/python"
}
build_sources() {
    echo build >> "$PREFIX/events"
    if [[ ! -f "$PREFIX/failed-once" ]]; then
        touch "$PREFIX/failed-once"
        return 17
    fi
}
check_environment() {
    echo check >> "$PREFIX/events"
    if [[ -f "$PREFIX/fail-check" ]]; then return 19; fi
    printf '{"ready":true,"smoke":true,"exports":[{"trim":true},{"trim":false}]}' > "$PREFIX/last-smoke.json"
}
main --prefix "$2" --manifest "$3"
'''
    command = ["bash", "-c", body, "bash", str(INSTALLER), str(prefix), str(ROOT / "setup/versions.json")]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 17
    assert not (prefix / "receipt.json").exists()
    second = subprocess.run(command, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    receipt = json.loads((prefix / "receipt.json").read_text())
    assert receipt["ready"] is True
    third = subprocess.run(command, capture_output=True, text=True)
    assert third.returncode == 0, third.stderr
    assert (prefix / "events").read_text().splitlines() == [
        "system", "conda", "environment", "build", "system", "conda", "environment", "build", "check", "check",
    ]
    original_receipt = (prefix / "receipt.json").read_bytes()
    (prefix / "fail-check").touch()
    failed_recheck = subprocess.run(command, capture_output=True, text=True)
    assert failed_recheck.returncode != 0
    assert (prefix / "receipt.json").read_bytes() == original_receipt
    assert (prefix / "events").read_text().splitlines()[-1] == "check"


def test_installer_never_executes_download_with_wrong_checksum(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    curl = commands / "curl"
    curl.write_text(
        f"#!{sys.executable}\nimport pathlib,sys\n"
        "pathlib.Path(sys.argv[sys.argv.index('--output')+1]).write_text('touch '+repr(sys.argv[-1]))\n"
    )
    curl.chmod(0o755)
    prefix = tmp_path / "managed"
    prefix.mkdir()
    sentinel = tmp_path / "executed-unverified-installer"
    body = r'''
source "$1"
PREFIX="$2"
ENVIRONMENT="$PREFIX/envs/nksr"
MINIFORGE_URL="$3"
MINIFORGE_SHA="0000000000000000000000000000000000000000000000000000000000000000"
bootstrap_conda
'''
    result = subprocess.run([
        "bash", "-c", body, "bash", str(INSTALLER), str(prefix), str(sentinel),
    ], env={**os.environ, "PATH": f"{commands}:{os.environ['PATH']}"}, capture_output=True, text=True)
    assert result.returncode != 0
    assert not sentinel.exists()
    assert "FAILED" in result.stdout or "did NOT match" in result.stderr


def test_installer_checks_with_cold_worker_environment(tmp_path):
    prefix = tmp_path / "managed"
    environment = prefix / "envs/nksr"
    (environment / "bin").mkdir(parents=True)
    python = environment / "bin/python"
    python.write_text(
        f"#!{sys.executable}\nimport json,os\n"
        "assert 'LD_LIBRARY_PATH' not in os.environ\n"
        "assert 'CUDA_HOME' not in os.environ\n"
        "assert 'PYTHONPATH' not in os.environ\n"
        f"assert {str(environment)!r} not in os.environ['PATH']\n"
        "print(json.dumps({'ready':True,'smoke':True,'exports':[{'trim':True},{'trim':False}]}))\n"
    )
    python.chmod(0o755)
    body = r'''
source "$1"
PREFIX="$2"
ENVIRONMENT="$PREFIX/envs/nksr"
MANIFEST="$3"
export CUDA_HOME="$ENVIRONMENT" LD_LIBRARY_PATH="$ENVIRONMENT/lib" PYTHONPATH=build-only
export PATH="$ENVIRONMENT/bin:$PATH"
check_environment
'''
    result = subprocess.run([
        "bash", "-c", body, "bash", str(INSTALLER), str(prefix), str(ROOT / "setup/versions.json"),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads((prefix / "last-smoke.json").read_text())["ready"] is True


def test_bad_download_is_preserved_but_retry_does_not_resume_corrupt_bytes(tmp_path):
    commands = tmp_path / "commands"
    commands.mkdir()
    payload = tmp_path / "verified-installer"
    payload.write_text('#!/bin/bash\nmkdir -p "$4/bin"\ntouch "$4/bin/conda"\nchmod +x "$4/bin/conda"\n')
    checksum = hashlib.sha256(payload.read_bytes()).hexdigest()
    counter = tmp_path / "already-downloaded"
    offsets = tmp_path / "resume-offsets"
    curl = commands / "curl"
    curl.write_text(
        f"#!{sys.executable}\nimport pathlib,sys\n"
        "target=pathlib.Path(sys.argv[sys.argv.index('--output')+1])\n"
        f"counter=pathlib.Path({str(counter)!r})\n"
        f"with pathlib.Path({str(offsets)!r}).open('a') as log: log.write(str(target.stat().st_size if target.exists() else 0)+'\\n')\n"
        f"data=pathlib.Path({str(payload)!r}).read_bytes() if counter.exists() else b'wrong download'\n"
        "with target.open('ab') as stream: stream.write(data)\n"
        "counter.touch()\n"
    )
    curl.chmod(0o755)
    prefix = tmp_path / "managed"
    prefix.mkdir()
    body = r'''
source "$1"
PREFIX="$2"
ENVIRONMENT="$PREFIX/envs/nksr"
MINIFORGE_URL=https://example.invalid/miniforge
MINIFORGE_SHA="$3"
bootstrap_conda
'''
    command = ["bash", "-c", body, "bash", str(INSTALLER), str(prefix), checksum]
    environment = {**os.environ, "PATH": f"{commands}:{os.environ['PATH']}"}
    first = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert first.returncode != 0
    quarantined, = (prefix / "downloads").glob("miniforge-rejected.*")
    assert quarantined.read_bytes() == b"wrong download"
    assert not (prefix / "conda/bin/conda").exists()
    second = subprocess.run(command, env=environment, capture_output=True, text=True)
    assert second.returncode == 0, second.stderr
    assert offsets.read_text().splitlines() == ["0", "0"]
    assert (prefix / "conda/bin/conda").exists()
