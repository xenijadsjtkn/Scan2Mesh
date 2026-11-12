"""Default launch, cancellation and Windows bootstrap contract without a real GUI."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from scan2mesh import cli, desktop, nksr_runtime, pipeline


def forbid_processing(*args, **kwargs):
    pytest.fail("This action must not start processing")


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    root = tmp_path / "output"
    monkeypatch.setattr(desktop, "RUNS_ROOT", root)
    return root


def test_cancel_does_not_start_wsl_or_create_output(runs_root, monkeypatch):
    monkeypatch.setattr(desktop, "choose_scan_file", lambda: None)
    monkeypatch.setattr(nksr_runtime, "run_direct", forbid_processing)
    assert desktop.main([]) is None
    assert not runs_root.exists()


def test_play_routes_original_unicode_file_to_direct_nksr(runs_root, tmp_path, monkeypatch, capsys):
    source = tmp_path / "Hälle & $(Test) 'Messung'.pts"
    source.write_text("original measurements")
    calls = []
    monkeypatch.setattr(desktop, "choose_scan_file", lambda: source)
    monkeypatch.setattr(pipeline, "run_pipeline", forbid_processing)

    def run(source_path, output_root, **options):
        calls.append((source_path, output_root, options))
        return output_root / "nksr-direkt-test" / "mesh_colored.ply"

    monkeypatch.setattr(nksr_runtime, "run_direct", run)
    result = desktop.main([])
    assert calls == [(source.resolve(), runs_root, {"units": "m", "python": None, "wsl_distro": None})]
    assert result == runs_root / "nksr-direkt-test"
    assert source.read_text() == "original measurements"
    output = capsys.readouterr().out
    assert "Detailstufe 1.0" in output
    assert "Beide Exporte" in output
    assert "Fertig:" in output


@pytest.mark.parametrize("entry", ["desktop", "cli", "process"])
def test_all_entry_points_forward_units_output_and_existing_interpreter(
    entry, runs_root, tmp_path, monkeypatch,
):
    source = tmp_path / "scan.pts"
    source.write_text("original measurements")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(desktop, "choose_scan_file", forbid_processing)
    calls = []

    def run(source_path, output_root, **options):
        calls.append((source_path, output_root, options))
        return output_root / "nksr-direkt-test" / "mesh_raw.ply"

    monkeypatch.setattr(nksr_runtime, "run_direct", run)
    options = ["--units", "mm", "--output-root", "Ergebnisse Ä", "--nksr-python", "/home/user/envs/nksr/bin/python", "--nksr-wsl-distro", "Ubuntu-Test"]
    if entry == "desktop":
        result = desktop.main(["--input", str(source), *options])
    elif entry == "cli":
        result = cli.main(["--input", str(source), *options])
    else:
        result = cli.main(["process", str(source), *options])
    assert calls == [(source.resolve(), tmp_path / "Ergebnisse Ä", {"units": "mm", "python": "/home/user/envs/nksr/bin/python", "wsl_distro": "Ubuntu-Test"})]
    if entry == "desktop":
        assert result == tmp_path / "Ergebnisse Ä" / "nksr-direkt-test"
    else:
        # Installed console scripts call sys.exit(main()); a Path signals failure.
        assert result is None
    assert not runs_root.exists()


@pytest.mark.parametrize("kind", ["missing", "directory", "unsupported"])
def test_invalid_input_does_not_start_backend_or_create_output(kind, runs_root, tmp_path, monkeypatch):
    source = tmp_path / ("scan.e57" if kind == "unsupported" else "scan.pts")
    if kind == "directory":
        source.mkdir()
    elif kind == "unsupported":
        source.write_text("not directly supported")
    monkeypatch.setattr(nksr_runtime, "run_direct", forbid_processing)
    with pytest.raises(SystemExit) as error:
        desktop.main(["--input", str(source)])
    assert error.value.code == 2
    assert not runs_root.exists()


def test_picker_failure_creates_no_output(runs_root, monkeypatch, capsys):
    def fail():
        raise RuntimeError("Dateiauswahl: kein Desktop")
    monkeypatch.setattr(desktop, "choose_scan_file", fail)
    monkeypatch.setattr(nksr_runtime, "run_direct", forbid_processing)
    with pytest.raises(SystemExit) as error:
        desktop.main([])
    assert error.value.code == 2
    assert "kein Desktop" in capsys.readouterr().err
    assert not runs_root.exists()


def test_backend_failure_has_no_classical_fallback(runs_root, tmp_path, monkeypatch, capsys):
    source = tmp_path / "scan.pts"
    source.write_text("original measurements")
    def fail(*args, **kwargs):
        raise RuntimeError("CUDA out of memory")
    monkeypatch.setattr(nksr_runtime, "run_direct", fail)
    monkeypatch.setattr(pipeline, "run_pipeline", forbid_processing)
    with pytest.raises(SystemExit) as error:
        desktop.main(["--input", str(source)])
    output = capsys.readouterr()
    assert error.value.code == 2
    assert "CUDA out of memory" in output.err
    assert "Fertig:" not in output.out


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


def test_windows_default_output_uses_local_app_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_data = tmp_path / "Lokale Daten Ä"
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))

    destination = desktop.default_runs_root()

    assert destination == local_data / "Scan2Mesh"
    assert not local_data.exists()


def test_windows_output_falls_back_to_local_user_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_home = tmp_path / "user-home"
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))

    destination = desktop.default_runs_root()

    assert destination == user_home / "AppData" / "Local" / "Scan2Mesh"
    assert not user_home.exists()


def test_non_windows_default_output_stays_in_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop.sys, "platform", "linux")

    assert desktop.default_runs_root() == Path(desktop.__file__).resolve().parents[2] / "runs"
