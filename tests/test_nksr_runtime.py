"""Exercise process boundaries without requiring WSL, CUDA or NKSR."""

import json
from pathlib import Path
import subprocess

import pytest

from scan2mesh import nksr_runtime as runtime


@pytest.fixture(autouse=True)
def isolated_configuration(monkeypatch):
    monkeypatch.delenv("SCAN2MESH_NKSR_PYTHON", raising=False)
    monkeypatch.delenv("SCAN2MESH_NKSR_WSL_DISTRO", raising=False)


@pytest.mark.parametrize("selection", ["explicit", "discover", "saved"])
def test_windows_paths_remain_arguments_and_both_exports_are_requested(
    tmp_path, monkeypatch, selection,
):
    source = tmp_path / "Muenchen Ä & $(Test) 'scan'.pts"
    source.write_text("fake point cloud")
    output_root = tmp_path / "Ergebnisse Ä"
    primary = output_root / "nksr-direkt-example" / "mesh_colored.ply"
    linux_primary = "/mnt/c/Ergebnisse Ä/nksr-direkt-example/mesh_colored.ply"
    interpreter = "/home/operator/miniforge3/envs/nksr/bin/python"
    conversions, worker_calls, captured = {}, [], []
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    expected_distro = "Scan2Mesh-NKSR" if selection == "saved" else "Ubuntu-22.04"
    if selection == "saved":
        local_data = tmp_path / "Local Data"
        monkeypatch.setenv("LOCALAPPDATA", str(local_data))
        config_path = local_data / "Scan2Mesh" / "backend.json"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(json.dumps({"schema_version": 1, "wsl_distro": expected_distro, "python": interpreter}))

    def run(command, **kwargs):
        assert command[:4] == ["wsl.exe", "--distribution", expected_distro, "--exec"]
        assert not kwargs.get("shell", False)
        if kwargs.get("capture_output"):
            captured.append(command)
            assert kwargs["encoding"] == "utf-8"
            if "wslpath" in command:
                if "-w" in command:
                    assert command[-1] == linux_primary
                    value = str(primary)
                else:
                    # A synthetic mapping keeps path spelling and argument
                    # separation observable without an actual Windows host.
                    value = "/mnt/c/" + command[-1]
                    conversions[value] = command[-1]
            else:
                assert command[4:6] == ["python3", "-c"]
                assert "import torch; import nksr" in command[-1]
                value = json.dumps([interpreter])
            return subprocess.CompletedProcess(command, 0, value + "\n", "")
        worker_calls.append(command)
        assert kwargs == {"check": True}
        assert command[4:8] == [interpreter, "-u", "-X", "utf8"]
        assert conversions[command[command.index("--input") + 1]] == str(source.resolve())
        assert command[command.index("--detail-level") + 1] == "1.0"
        assert "--compare-trim" in command
        assert command[command.index("--units") + 1] == "mm"
        assert conversions[command[command.index("--output-root") + 1]] == str(output_root)
        report = Path(conversions[command[command.index("--result-file") + 1]])
        primary.parent.mkdir(parents=True)
        primary.write_text("completed mesh")
        report.write_text(json.dumps({"mesh_path": linux_primary}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runtime.subprocess, "run", run)

    actual = runtime.run_direct(
        source, output_root, units="mm", python=interpreter if selection == "explicit" else None,
    )

    assert actual == primary
    assert len(worker_calls) == 1
    assert any("python3" in c for c in captured) == (selection == "discover")
    assert not list(output_root.glob(".nksr-launch-*"))


@pytest.mark.parametrize("candidates", [[], ["/first/bin/python", "/second/bin/python"]])
def test_missing_or_ambiguous_environment_does_not_start_run(
    tmp_path, monkeypatch, candidates,
):
    source = tmp_path / "scan.ply"
    source.write_text("placeholder")
    destination = tmp_path / "never-created"
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert "python3" in command
        assert kwargs["capture_output"]
        return subprocess.CompletedProcess(command, 0, json.dumps(candidates), "")

    monkeypatch.setattr(runtime.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="SCAN2MESH_NKSR_PYTHON"):
        runtime.run_direct(source, destination)

    assert len(commands) == 1
    assert not destination.exists()


def test_backend_failure_preserves_partial_artifacts_without_fallback(tmp_path, monkeypatch):
    source = tmp_path / "scan.ply"
    source.write_text("placeholder")
    destination = tmp_path / "runs"
    artifact = destination / "nksr-direkt-partial" / "nksr_raw.npz"
    calls = []
    monkeypatch.setattr(runtime.sys, "platform", "linux")

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs == {"check": True}
        assert command[0] == "/existing/nksr/bin/python"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"raw geometry")
        raise subprocess.CalledProcessError(23, command)

    monkeypatch.setattr(runtime.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="Exitcode 23"):
        runtime.run_direct(source, destination, python="/existing/nksr/bin/python")

    assert len(calls) == 1
    assert artifact.read_bytes() == b"raw geometry"
    assert not list(destination.glob(".nksr-launch-*"))


def test_configured_environment_is_reused_and_missing_result_is_reported(tmp_path, monkeypatch):
    source = tmp_path / "scan.ply"
    source.write_text("placeholder")
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setenv("SCAN2MESH_NKSR_PYTHON", "/configured/nksr/python")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        assert kwargs == {"check": True}
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runtime.subprocess, "run", run)

    with pytest.raises(RuntimeError, match="keinen lesbaren Ergebnispfad"):
        runtime.run_direct(source, tmp_path / "runs")

    assert len(commands) == 1
    assert commands[0][0] == "/configured/nksr/python"


def test_linux_handoff_returns_worker_mesh_and_removes_temporary_metadata(tmp_path, monkeypatch):
    source = tmp_path / "scan with spaces.ply"
    source.write_text("placeholder")
    destination = tmp_path / "runs"
    primary = destination / "nksr-direkt-example" / "mesh_raw.ply"
    monkeypatch.setattr(runtime.sys, "platform", "linux")
    monkeypatch.setenv("SCAN2MESH_NKSR_PYTHON", "/configured/nksr/python")

    def run(command, **kwargs):
        assert kwargs == {"check": True}
        assert command[0] == "/explicit/nksr/python"
        assert command[command.index("--input") + 1] == str(source)
        primary.parent.mkdir(parents=True)
        primary.write_text("complete mesh")
        result_file = Path(command[command.index("--result-file") + 1])
        result_file.write_text(json.dumps({"mesh_path": str(primary)}), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runtime.subprocess, "run", run)

    assert runtime.run_direct(source, destination, python="/explicit/nksr/python") == primary
    assert primary.read_text() == "complete mesh"
    assert not list(destination.glob(".nksr-launch-*"))


def test_windows_setup_configuration_is_read_without_global_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    config_path = tmp_path / "Scan2Mesh" / "backend.json"
    config_path.parent.mkdir()
    config = {"schema_version": 1, "wsl_distro": "Scan2Mesh-NKSR", "python": "/opt/scan2mesh/envs/nksr/bin/python"}
    # Windows PowerShell 5 writes a UTF-8 BOM by default.
    config_path.write_text(json.dumps(config), encoding="utf-8-sig")
    assert runtime._saved_backend() == config


@pytest.mark.parametrize("config", [
    {"schema_version": 1, "wsl_distro": "Scan2Mesh-NKSR", "python": "python"},
    {"schema_version": 2, "wsl_distro": "Scan2Mesh-NKSR", "python": "/opt/nksr/python"},
    {"schema_version": 1, "python": "/opt/nksr/python"},
    [],
])
def test_invalid_setup_config_fails_before_backend_or_output(tmp_path, monkeypatch, config):
    monkeypatch.setattr(runtime.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    source = tmp_path / "scan.pts"
    source.touch()
    config_path = tmp_path / "Scan2Mesh" / "backend.json"
    config_path.parent.mkdir()
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(runtime.subprocess, "run", lambda *a, **kw: pytest.fail("Invalid setup must not launch WSL"))
    with pytest.raises(RuntimeError, match="Einrichten.cmd"):
        runtime.run_direct(source, tmp_path / "output")
    assert not (tmp_path / "output").exists()
