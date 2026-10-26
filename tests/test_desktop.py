"""Desktop-start behavior without opening a real GUI or executing PowerShell."""

import importlib.util
import json
import subprocess
from pathlib import Path

import numpy as np
import open3d as o3d
import pytest

from scan2mesh import demo, desktop, pipeline


@pytest.fixture
def runs_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    destination = tmp_path / "desktop-runs"
    monkeypatch.setattr(desktop, "RUNS_ROOT", destination)
    return destination


def stub_processing(monkeypatch: pytest.MonkeyPatch, implementation) -> None:
    """Support either a module-level alias or a lazy processing import."""
    monkeypatch.setattr(pipeline, "run_pipeline", implementation)
    if hasattr(desktop, "run_pipeline"):
        monkeypatch.setattr(desktop, "run_pipeline", implementation)


def stub_demo(monkeypatch: pytest.MonkeyPatch, implementation) -> None:
    monkeypatch.setattr(demo, "generate_demo", implementation)
    if hasattr(desktop, "generate_demo"):
        monkeypatch.setattr(desktop, "generate_demo", implementation)


def forbid_processing(*args, **kwargs):
    pytest.fail("Cancellation or invalid input must not start processing")


def test_no_arguments_cancel_without_processing_or_outputs(
    runs_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setattr(desktop, "choose_scan_file", lambda: None)
    stub_processing(monkeypatch, forbid_processing)
    stub_demo(monkeypatch, forbid_processing)

    assert desktop.main([]) is None

    assert not runs_root.exists()
    output = capsys.readouterr().out.lower()
    assert any(word in output for word in ("abbruch", "abgebrochen", "cancel", "keine datei"))


def test_selected_unicode_path_is_passed_unchanged_to_processing(
    tmp_path: Path, runs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "München Halle 3 & $(Test) 'Messung'.ply"
    source.write_text("placeholder: processing is mocked\n")
    calls = []
    monkeypatch.setattr(desktop, "choose_scan_file", lambda: source)

    def process(input_path, output, config):
        calls.append((input_path, output, config))
        return {"counts": {"mesh_triangles": 1}}

    stub_processing(monkeypatch, process)
    stub_demo(monkeypatch, forbid_processing)

    result = desktop.main([])

    assert len(calls) == 1
    actual_source, output, config = calls[0]
    assert actual_source == source.resolve()
    assert result == output
    assert result.parent.parent == runs_root
    assert result.parent.name.startswith("vscode-scan-")
    assert result.name == "result"
    assert config.voxel_size == 0.01
    assert config.plane_distance == 0.01


@pytest.mark.parametrize("units, expected_scale", [("m", 0.01), ("mm", 10)])
def test_explicit_input_bypasses_picker_and_respects_units(
    tmp_path: Path,
    runs_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    units: str,
    expected_scale: float,
) -> None:
    source = tmp_path / "scan.ply"
    source.write_text("placeholder\n")
    calls = []
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_processing)

    def process(input_path, output, config):
        calls.append(config)
        return {"counts": {"mesh_triangles": 1}}

    stub_processing(monkeypatch, process)

    desktop.main(["--input", str(source), "--units", units])

    assert len(calls) == 1
    assert calls[0].voxel_size == expected_scale
    assert calls[0].plane_distance == expected_scale


def test_demo_is_explicit_and_uses_demo_parameters(
    runs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated, processed = [], []
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_processing)

    def generate(path):
        generated.append(path)
        path.write_text("demo placeholder\n")

    def process(input_path, output, config):
        processed.append((input_path, output, config))
        return {"counts": {"mesh_triangles": 1}}

    stub_demo(monkeypatch, generate)
    stub_processing(monkeypatch, process)

    result = desktop.main(["--demo"])

    assert len(generated) == len(processed) == 1
    assert generated[0] == processed[0][0]
    assert generated[0].parent == result.parent
    assert result.parent.name.startswith("vscode-demo-")
    assert processed[0][2].voxel_size == 0.025
    assert processed[0][2].plane_distance == 0.015


def test_demo_and_input_are_mutually_exclusive(
    runs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_processing(monkeypatch, forbid_processing)
    stub_demo(monkeypatch, forbid_processing)

    with pytest.raises(SystemExit) as error:
        desktop.main(["--demo", "--input", "scan.ply"])

    assert error.value.code == 2
    assert not runs_root.exists()


def test_picker_failure_is_actionable_without_creating_run(
    runs_root: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    def unavailable():
        raise RuntimeError("Dateiauswahl-Test: kein grafischer Desktop")

    monkeypatch.setattr(desktop, "choose_scan_file", unavailable)
    stub_processing(monkeypatch, forbid_processing)

    with pytest.raises(SystemExit) as error:
        desktop.main([])

    assert error.value.code == 2
    assert "Dateiauswahl-Test" in capsys.readouterr().err
    assert not runs_root.exists()


@pytest.mark.parametrize("input_kind", ["missing", "directory"])
def test_invalid_input_is_rejected_before_creating_run(
    tmp_path: Path,
    runs_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
    input_kind: str,
) -> None:
    source = tmp_path / "invalid-input.ply"
    if input_kind == "directory":
        source.mkdir()
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_processing)
    stub_processing(monkeypatch, forbid_processing)

    with pytest.raises(SystemExit) as error:
        desktop.main(["--input", str(source)])

    assert error.value.code == 2
    assert source.name in capsys.readouterr().err
    assert not runs_root.exists()


@pytest.mark.parametrize(
    "platform, expected", [("win32", "windows"), ("linux", "tk"), ("darwin", "tk")]
)
def test_picker_uses_platform_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str, expected: str
) -> None:
    selected = tmp_path / "selected.ply"
    calls = []

    def windows():
        calls.append("windows")
        return selected

    def tk():
        calls.append("tk")
        return selected

    monkeypatch.setattr(desktop.sys, "platform", platform)
    monkeypatch.setattr(desktop, "_pick_windows_scan", windows)
    monkeypatch.setattr(desktop, "_pick_tk_scan", tk)

    assert desktop.choose_scan_file() == selected
    assert calls == [expected]


@pytest.mark.parametrize(
    "selection",
    ["C:\\Scans\\Hälle & $(Test)\\Mäßige Auflösung 1.ply", None],
    ids=["unicode-path", "cancel"],
)
def test_windows_picker_uses_static_command_and_utf8_without_shell(
    monkeypatch: pytest.MonkeyPatch, selection: str | None
) -> None:
    calls = []
    if hasattr(desktop, "shutil"):
        monkeypatch.setattr(desktop.shutil, "which", lambda executable: executable)

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, (selection or "") + "\n", "")

    monkeypatch.setattr(desktop.subprocess, "run", run)

    assert desktop._pick_windows_scan() == (Path(selection) if selection else None)

    assert len(calls) == 1
    command, options = calls[0]
    assert isinstance(command, (list, tuple))
    assert options.get("shell", False) is False
    assert options["encoding"].lower().replace("-", "") == "utf8"
    assert "-sta" in [arg.lower() for arg in command]
    assert "OpenFileDialog" in " ".join(command)
    if selection:
        assert selection not in " ".join(command)


def test_windows_picker_reports_powershell_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    if hasattr(desktop, "shutil"):
        monkeypatch.setattr(desktop.shutil, "which", lambda executable: executable)

    def run(command, **kwargs):
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(1, command, stderr="WinForms unavailable")
        return subprocess.CompletedProcess(command, 1, "", "WinForms unavailable")

    monkeypatch.setattr(desktop.subprocess, "run", run)

    with pytest.raises((OSError, RuntimeError)):
        desktop._pick_windows_scan()


def test_real_own_scan_produces_fresh_results_on_each_start(
    tmp_path: Path, runs_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    index = np.arange(1_200)
    z = 1 - 2 * (index + 0.5) / len(index)
    theta = np.pi * (3 - np.sqrt(5)) * index
    radius = np.sqrt(1 - z**2)
    points = np.column_stack((radius * np.cos(theta), radius * np.sin(theta), z))
    # Match a measured scan rather than an exactly co-spherical Delaunay input.
    points += np.random.default_rng(41).normal(0, 0.0005, points.shape)
    source = tmp_path / "Eigener Scan Ä.ply"
    cloud = o3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    assert o3d.io.write_point_cloud(str(source), cloud)
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_processing)

    first = desktop.main(["--input", str(source)])
    original_mesh = (first / "mesh.ply").read_bytes()
    second = desktop.main(["--input", str(source)])

    assert first != second
    assert first.parent.parent == second.parent.parent == runs_root
    assert (first / "mesh.ply").read_bytes() == original_mesh
    for result in (first, second):
        assert result.name == "result"
        assert (result / "mesh.ply").stat().st_size > 0
        report = json.loads((result / "report.json").read_text())
        assert report["input_path"] == str(source.resolve())
        assert report["counts"]["mesh_triangles"] > 1_000
        assert report["quality"]["point_to_mesh"]["p95"] < 0.08


def load_project_bootstrap():
    entry = Path(__file__).resolve().parents[1] / "main.py"
    specification = importlib.util.spec_from_file_location("scan2mesh_bootstrap_test", entry)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_bootstrap_uses_project_environment_even_when_application_is_importable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_project_bootstrap()
    project = Path(launcher.__file__).resolve().parent
    caller = tmp_path / "outside-checkout"
    caller.mkdir()
    monkeypatch.chdir(caller)
    monkeypatch.setattr(launcher.sys, "prefix", str(tmp_path / "global-python"))
    arguments = ["main.py", "--input", "Hälle Messung 1.ply", "--units", "mm"]
    monkeypatch.setattr(launcher.sys, "argv", arguments)
    # The application is already imported in this interpreter; this must not
    # bypass synchronization and silently select a global package installation.
    monkeypatch.setattr(desktop, "main", forbid_processing)
    calls = []

    def run(command, **options):
        calls.append((command, options.get("cwd"), options.get("check")))
        return subprocess.CompletedProcess(command, 0 if command[0] == "uv" else 7)

    monkeypatch.setattr(launcher.subprocess, "run", run)

    with pytest.raises(SystemExit) as error:
        launcher.main()

    assert error.value.code == 7
    assert len(calls) == 2
    assert calls[0] == (["uv", "sync", "--frozen"], project, True)
    python = project / ".venv" / (
        "Scripts/python.exe" if launcher.os.name == "nt" else "bin/python"
    )
    assert calls[1][0] == [str(python), "-m", "scan2mesh.desktop", *arguments[1:]]
    assert calls[1][1] == caller


def test_bootstrap_inside_project_environment_calls_application_directly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    launcher = load_project_bootstrap()
    project = Path(launcher.__file__).resolve().parent
    monkeypatch.setattr(launcher.sys, "prefix", str(project / ".venv"))
    marker = tmp_path / "result"
    monkeypatch.setattr(desktop, "main", lambda: marker)
    monkeypatch.setattr(launcher.subprocess, "run", forbid_processing)

    assert launcher.main() == marker
