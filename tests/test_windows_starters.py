"""Run the real PowerShell starter with fake native executables on Linux."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest


PROJECT = Path(__file__).resolve().parents[1]
PWSH = os.environ.get('SCAN2MESH_PWSH') or shutil.which('pwsh')
pytestmark = pytest.mark.skipif(
    not PWSH or sys.platform == 'win32',
    reason='These process tests use Linux fake executables; set SCAN2MESH_PWSH on Linux/WSL',
)


def powershell(script, *args, env):
    return subprocess.run(
        [PWSH, '-NoLogo', '-NoProfile', '-File', str(script), *map(str, args)],
        env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.fixture
def starter_environment(tmp_path):
    environment = os.environ.copy()
    for name in ('SCAN2MESH_NKSR_PYTHON', 'SCAN2MESH_NKSR_WSL_DISTRO'):
        environment.pop(name, None)
    for name in ('XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME'):
        path = tmp_path / name
        path.mkdir()
        environment[name] = str(path)
    environment['LOCALAPPDATA'] = str(tmp_path / 'Local Data Ä')
    environment['SCAN2MESH_START_EVENTS'] = str(tmp_path / 'events.jsonl')
    environment['VIRTUAL_ENV'] = 'old-checkout-environment'
    return environment


def fake_native(path, event_name, tmp_path):
    implementation = tmp_path / f'{event_name}.py'
    implementation.write_text(
        'import json, os, sys\n'
        'with open(os.environ["SCAN2MESH_START_EVENTS"], "a", encoding="utf-8") as stream:\n'
        f'    stream.write(json.dumps({{"event": {event_name!r}, "args": sys.argv[1:], "environment": os.environ.get("UV_PROJECT_ENVIRONMENT"), "active": os.environ.get("VIRTUAL_ENV")}}) + "\\n")\n',
        encoding='utf-8',
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(implementation))} "$@"\n')
    path.chmod(0o755)


def test_double_click_starter_uses_prepared_backend_and_literal_paths(tmp_path, starter_environment):
    root = Path(starter_environment['LOCALAPPDATA']) / 'Scan2Mesh'
    fake_native(root / 'tools' / 'uv.exe', 'uv', tmp_path)
    fake_native(root / 'venv' / 'Scripts' / 'python.exe', 'frontend', tmp_path)
    backend = {'schema_version': 1, 'wsl_distro': 'Scan2Mesh-NKSR', 'python': '/opt/scan2mesh/envs/nksr/bin/python'}
    (root / 'backend.json').write_text(json.dumps(backend), encoding='utf-8-sig')
    source = tmp_path / "Messung Ä & $(Test) 'scan'.pts"
    destination = tmp_path / 'Eigene Ergebnisse Ä'

    result = powershell(
        PROJECT / 'scripts' / 'windows_start.ps1',
        '-InputFile', source, '-Units', 'mm', '-OutputRoot', destination,
        env=starter_environment,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    events = [json.loads(line) for line in Path(starter_environment['SCAN2MESH_START_EVENTS']).read_text().splitlines()]
    assert [event['event'] for event in events] == ['uv', 'frontend']
    assert events[0]['args'] == ['sync', '--frozen', '--no-dev', '--project', str(PROJECT), '--python', '3.12']
    assert all(event['environment'] == str(root / 'venv') and event['active'] is None for event in events)
    assert events[1]['args'] == [
        '-X', 'utf8', str(PROJECT / 'main.py'), '--units', 'mm', '--nksr-python', backend['python'],
        '--nksr-wsl-distro', backend['wsl_distro'], '--input', str(source), '--output-root', str(destination),
    ]
    assert json.loads((root / 'backend.json').read_text(encoding='utf-8-sig')) == backend


def test_starter_missing_setup_stops_without_launching_native_process(starter_environment):
    result = powershell(PROJECT / 'scripts' / 'windows_start.ps1', env=starter_environment)
    assert result.returncode == 1
    assert 'Einrichten.cmd' in result.stdout
    assert not Path(starter_environment['SCAN2MESH_START_EVENTS']).exists()


def test_powershell_setup_reboot_retry_and_failure_contracts(starter_environment):
    result = powershell(PROJECT / 'tests' / 'windows_setup_tests.ps1', env=starter_environment)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS' in result.stdout
