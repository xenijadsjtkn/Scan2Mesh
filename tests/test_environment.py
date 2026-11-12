"""Windows setup must not update a virtual environment inside OneDrive."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from scan2mesh import desktop


def load_bootstrap():
    entry = Path(__file__).resolve().parents[1] / "main.py"
    specification = importlib.util.spec_from_file_location("scan2mesh_environment_test", entry)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_windows_project_environment_is_outside_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_bootstrap()
    project = tmp_path / "OneDrive" / "Scan2Mesh"
    local_data = tmp_path / "Lokale Daten Ä"
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))

    assert launcher.project_environment(project) == local_data / "Scan2Mesh" / "venv"
    assert not local_data.exists()


def test_windows_project_environment_uses_local_home_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_bootstrap()
    user_home = tmp_path / "user-home"
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))

    assert launcher.project_environment(tmp_path / "project") == (
        user_home / "AppData" / "Local" / "Scan2Mesh" / "venv"
    )
    assert not user_home.exists()


def test_non_windows_project_environment_stays_in_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_bootstrap()
    monkeypatch.setattr(launcher.sys, "platform", "linux")

    assert launcher.project_environment(tmp_path) == tmp_path / ".venv"


@pytest.mark.parametrize("custom_cache", [False, True], ids=["default-cache", "user-cache"])
def test_windows_bootstrap_leaves_old_onedrive_environment_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, custom_cache: bool
) -> None:
    launcher = load_bootstrap()
    project = tmp_path / "OneDrive" / "Scan2Mesh"
    old_environment = project / ".venv"
    marker = old_environment / "Lib" / "site-packages" / "scan2mesh.dist-info" / "INSTALLER"
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"locked existing installation\n")
    local_data = tmp_path / "Local Data Ä"
    target_environment = local_data / "Scan2Mesh" / "venv"
    caller = tmp_path / "working-directory"
    caller.mkdir()
    monkeypatch.chdir(caller)
    monkeypatch.setattr(launcher, "__file__", str(project / "main.py"))
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.sys, "prefix", str(old_environment))
    arguments = ["main.py", "--input", "Hälle Messung 1.e57", "--units", "mm"]
    monkeypatch.setattr(launcher.sys, "argv", arguments)
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    cache = tmp_path / "user-selected-cache" if custom_cache else local_data / "Scan2Mesh" / "cache" / "uv"
    if custom_cache:
        monkeypatch.setenv("UV_CACHE_DIR", str(cache))
    else:
        monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    # An inherited setting must not redirect this Windows setup back to OneDrive.
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(old_environment))
    monkeypatch.setattr(desktop, "main", lambda: pytest.fail("Do not run from the old environment"))
    calls = []

    def run(command, **options):
        environment = options["env"]
        calls.append(
            (
                command,
                options.get("cwd"),
                options.get("check"),
                environment.get("UV_PROJECT_ENVIRONMENT"),
                environment.get("UV_CACHE_DIR"),
            )
        )
        return subprocess.CompletedProcess(command, 0 if command[0] == "uv" else 23)

    monkeypatch.setattr(launcher.subprocess, "run", run)

    with pytest.raises(SystemExit) as error:
        launcher.main()

    assert error.value.code == 23
    assert len(calls) == 2
    assert calls[0][:3] == (["uv", "sync", "--frozen"], project, True)
    assert calls[1][0] == [
        str(target_environment / "Scripts" / "python.exe"),
        "-m", "scan2mesh.desktop", *arguments[1:],
    ]
    assert calls[1][1] == caller
    for call in calls:
        assert call[3] == str(target_environment)
        assert call[4] == str(cache)
    assert marker.read_bytes() == b"locked existing installation\n"
    assert [path for path in old_environment.rglob("*") if path.is_file()] == [marker]


def test_windows_bootstrap_inside_external_environment_runs_application_directly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = load_bootstrap()
    project = tmp_path / "OneDrive" / "Scan2Mesh"
    local_data = tmp_path / "LocalData"
    external = local_data / "Scan2Mesh" / "venv"
    monkeypatch.setattr(launcher, "__file__", str(project / "main.py"))
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.sys, "prefix", str(external))
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    result = tmp_path / "result"
    monkeypatch.setattr(desktop, "main", lambda: result)
    monkeypatch.setattr(
        launcher.subprocess, "run", lambda *args, **kwargs: pytest.fail("Do not resynchronize an active environment")
    )

    assert launcher.main() == result


def test_windows_vscode_launch_and_setup_task_use_the_same_external_environment() -> None:
    project = Path(__file__).resolve().parents[1]
    launch = json.loads((project / ".vscode" / "launch.json").read_text())
    tasks = json.loads((project / ".vscode" / "tasks.json").read_text())
    tasks_by_label = {task["label"]: task for task in tasks["tasks"]}
    expected_environment = "${env:LOCALAPPDATA}/Scan2Mesh/venv"
    expected_cache = "${env:LOCALAPPDATA}/Scan2Mesh/cache/uv"

    for configuration in launch["configurations"]:
        assert configuration["windows"]["python"].replace("\\", "/") == (
            expected_environment + "/Scripts/python.exe"
        )
        assert configuration["python"].replace("\\", "/") == "${workspaceFolder}/.venv/bin/python"
        task = tasks_by_label[configuration["preLaunchTask"]]
        assert task["windows"]["command"] == "powershell.exe"
        assert task["windows"]["args"] == [
            "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            "${workspaceFolder}/scripts/prepare_frontend.ps1",
        ]
        windows_environment = dict(task.get("options", {}).get("env", {}))
        windows_environment.update(task["windows"].get("options", {}).get("env", {}))
        assert windows_environment["UV_PROJECT_ENVIRONMENT"].replace("\\", "/") == expected_environment
        assert windows_environment["UV_CACHE_DIR"].replace("\\", "/") == expected_cache
        base_environment = task.get("options", {}).get("env", {}).get("UV_PROJECT_ENVIRONMENT")
        assert base_environment in (None, "${workspaceFolder}/.venv")


def test_play_bootstrap_reuses_managed_uv_without_global_install(tmp_path, monkeypatch):
    launcher = load_bootstrap()
    local_data = tmp_path / "Lokale Daten Ä"
    uv = local_data / "Scan2Mesh" / "tools" / "uv.exe"
    uv.parent.mkdir(parents=True)
    uv.touch()
    monkeypatch.setenv("LOCALAPPDATA", str(local_data))
    monkeypatch.setattr(launcher.sys, "platform", "win32")
    monkeypatch.setattr(launcher.sys, "prefix", str(tmp_path / "global-python"))
    monkeypatch.setattr(launcher.sys, "argv", ["main.py"])
    calls = []

    def run(command, **options):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    with pytest.raises(SystemExit) as result:
        launcher.main()
    assert result.value.code == 0
    assert calls[0] == [str(uv), "sync", "--frozen"]
    assert calls[1][0] == str(local_data / "Scan2Mesh" / "venv" / "Scripts" / "python.exe")
