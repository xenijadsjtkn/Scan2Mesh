#!/usr/bin/env bash
# Install only inside the dedicated, explicitly selected Scan2Mesh WSL distro.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REQUIREMENTS="$SCRIPT_DIR/../setup/nksr-requirements.txt"
CHECKER="$SCRIPT_DIR/check_nksr.py"

log() { printf '%s\n' "$*" >&2; }
die() { log "Scan2Mesh-Installation: $*"; exit 1; }

require_platform() {
    [[ "$(id -u)" == 0 ]] || die "In der eigenen WSL-Distribution als root starten."
    [[ "$(uname -m)" == x86_64 ]] || die "Der NKSR-Build benoetigt x86-64 Linux."
    # shellcheck disable=SC1091
    source /etc/os-release
    [[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || die "Diese Einrichtung ist fuer Ubuntu 22.04 vorgesehen."
}

claim_prefix() {
    [[ "$PREFIX" == /* && "$PREFIX" != / ]] || die "Ein absolutes, eigenes Installationsverzeichnis angeben."
    [[ ! -L "$PREFIX" ]] || die "Installationsverzeichnis darf kein symbolischer Link sein."
    local marker="$PREFIX/.scan2mesh-nksr-managed"
    if [[ -d "$PREFIX" && ! -f "$marker" ]]; then
        [[ -z "$(find "$PREFIX" -mindepth 1 -maxdepth 1 -print -quit)" ]] || die "Vorhandenes fremdes Verzeichnis bleibt unveraendert: $PREFIX"
    fi
    mkdir -p -- "$PREFIX"
    if [[ -e "$marker" ]]; then
        [[ ! -L "$marker" && "$(cat "$marker")" == 'Scan2Mesh NKSR v1' ]] || die "Unbekannte Besitzmarkierung: $marker"
    else
        printf '%s\n' 'Scan2Mesh NKSR v1' > "$marker"
    fi
}

install_system_packages() {
    log "Buildwerkzeuge und Laufzeitbibliotheken in der eigenen WSL-Distribution installieren ..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends python3 ca-certificates curl git build-essential \
        pkg-config libssl-dev libgl1 libglib2.0-0 libgomp1 libxrender1 libxext6
    # NVIDIA Linux display drivers are deliberately not installed in WSL.
}

load_manifest() {
    local settings
    settings="$(python3 - "$MANIFEST" "$REQUIREMENTS" "$CHECKER" "${BASH_SOURCE[0]}" <<'PY'
import hashlib, json, re, sys
from pathlib import Path
manifest = json.loads(Path(sys.argv[1]).read_text())
if manifest['schema_version'] != 1:
    raise SystemExit('Nicht unterstuetztes Setup-Manifest.')
values = [manifest['python'], manifest['torch'], manifest['cuda'], manifest['open3d'],
          manifest['miniforge']['url'], manifest['miniforge']['sha256'],
          manifest['nksr']['repository'], manifest['nksr']['revision'],
          manifest['pycg']['repository'], manifest['pycg']['revision'],
          manifest['nksr']['eigen_revision'], manifest['nksr']['openvdb_revision']]
if not re.fullmatch(r'[a-f0-9]{64}', values[5]):
    raise SystemExit('Ungueltige Miniforge-SHA256.')
for position in (7, 9, 10, 11):
    if not re.fullmatch(r'[a-f0-9]{40}', values[position]):
        raise SystemExit('Quellrevision muss ein vollstaendiger Commit-Hash sein.')
if any(not isinstance(v, str) or '\n' in v or '\r' in v for v in values):
    raise SystemExit('Ungueltiges Setup-Manifest.')
if not values[4].startswith('https://github.com/conda-forge/miniforge/releases/download/'):
    raise SystemExit('Miniforge muss aus dem offiziellen Release stammen.')
fingerprint = hashlib.sha256()
for path in sys.argv[1:]:
    fingerprint.update(Path(path).read_bytes())
print('\n'.join([*values, fingerprint.hexdigest()]))
PY
)"
    mapfile -t SETTINGS <<< "$settings"
    PYTHON_VERSION="${SETTINGS[0]}"; TORCH_VERSION="${SETTINGS[1]}"; CUDA_VERSION="${SETTINGS[2]}"
    MINIFORGE_URL="${SETTINGS[4]}"; MINIFORGE_SHA="${SETTINGS[5]}"
    NKSR_REPO="${SETTINGS[6]}"; NKSR_REV="${SETTINGS[7]}"
    PYCG_REPO="${SETTINGS[8]}"; PYCG_REV="${SETTINGS[9]}"
    EIGEN_REV="${SETTINGS[10]}"; OPENVDB_REV="${SETTINGS[11]}"; FINGERPRINT="${SETTINGS[12]}"
}

receipt_matches() {
    [[ -f "$PREFIX/receipt.json" && -x "$ENVIRONMENT/bin/python" ]] || return 1
    python3 - "$PREFIX/receipt.json" "$FINGERPRINT" "$ENVIRONMENT/bin/python" <<'PY'
import json, sys
try:
    receipt = json.load(open(sys.argv[1]))
    valid = receipt.get('fingerprint') == sys.argv[2] and receipt.get('python') == sys.argv[3] and receipt.get('ready') is True
except (OSError, ValueError):
    valid = False
raise SystemExit(0 if valid else 1)
PY
}

bootstrap_conda() {
    local installer="$PREFIX/downloads/miniforge-${MINIFORGE_SHA}.sh"
    local partial="${installer}.part" rejected
    [[ ! -L "$PREFIX/conda" && ! -L "$ENVIRONMENT" ]] || die "Verwaltete Umgebung darf kein symbolischer Link sein."
    mkdir -p "$PREFIX/downloads"
    if [[ ! -f "$installer" ]]; then
        curl --fail --location --retry 3 --continue-at - --output "$partial" "$MINIFORGE_URL"
        if ! printf '%s  %s\n' "$MINIFORGE_SHA" "$partial" | sha256sum --check -; then
            rejected="$(mktemp "$PREFIX/downloads/miniforge-rejected.XXXXXX")"
            mv -- "$partial" "$rejected"
            die "SHA256-Pruefung fehlgeschlagen. Datei bleibt unter $rejected erhalten; beim naechsten Start wird neu geladen."
        fi
        mv -- "$partial" "$installer"
    fi
    if ! printf '%s  %s\n' "$MINIFORGE_SHA" "$installer" | sha256sum --check -; then
        rejected="$(mktemp "$PREFIX/downloads/miniforge-rejected.XXXXXX")"
        mv -- "$installer" "$rejected"
        die "Beschaedigter Miniforge-Cache bleibt unter $rejected erhalten; Einrichtung erneut starten."
    fi
    if [[ ! -x "$PREFIX/conda/bin/conda" ]]; then
        # -u can finish an interrupted installer without deleting the prefix.
        bash "$installer" -b -u -p "$PREFIX/conda"
    fi
}

install_environment() {
    local operation=create
    [[ ! -f "$ENVIRONMENT/conda-meta/history" ]] || operation=install
    "$PREFIX/conda/bin/conda" "$operation" --yes --prefix "$ENVIRONMENT" --override-channels \
        --channel "nvidia/label/cuda-${CUDA_VERSION}.0" --channel conda-forge \
        "python=$PYTHON_VERSION" pip "cuda-nvcc=${CUDA_VERSION}.*" eigen=3.4 zlib \
        libcusparse-dev libcublas-dev libcusolver-dev
    export PATH="$ENVIRONMENT/bin:$PATH" CUDA_HOME="$ENVIRONMENT"
    export LD_LIBRARY_PATH="$ENVIRONMENT/lib:$ENVIRONMENT/targets/x86_64-linux/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export MAX_JOBS="${SCAN2MESH_BUILD_JOBS:-2}"
    "$ENVIRONMENT/bin/python" -m pip install --requirement "$REQUIREMENTS"
    "$ENVIRONMENT/bin/python" - "$TORCH_VERSION" <<'PY'
import sys, torch
assert torch.__version__ == sys.argv[1], 'Unerwartete PyTorch-Version'
assert torch.cuda.is_available(), 'Keine CUDA-GPU: Windows-Treiber und WSL2 pruefen.'
print('CUDA-GPU:', torch.cuda.get_device_name(0), flush=True)
PY
}

fetch_source() {
    local repository="$1" revision="$2" destination="$3"
    [[ ! -L "$destination" ]] || die "Quellverzeichnis darf kein symbolischer Link sein: $destination"
    if [[ ! -d "$destination/.git" ]]; then
        [[ ! -e "$destination" || -z "$(find "$destination" -mindepth 1 -maxdepth 1 -print -quit)" ]] || die "Fremde Quelldateien bleiben erhalten: $destination"
        mkdir -p "$destination"
        git -C "$destination" init
    fi
    if git -C "$destination" remote get-url origin >/dev/null 2>&1; then
        [[ "$(git -C "$destination" remote get-url origin)" == "$repository" ]] || die "Unerwartetes Quell-Repository: $destination"
    else
        git -C "$destination" remote add origin "$repository"
    fi
    if [[ "$(git -C "$destination" rev-parse HEAD 2>/dev/null || true)" != "$revision" ]]; then
        git -C "$destination" fetch --depth 1 origin "$revision"
        git -C "$destination" checkout --detach "$revision"
    fi
}

build_sources() {
    local nksr_source="$PREFIX/sources/NKSR-$NKSR_REV" pycg_source="$PREFIX/sources/PyCG-$PYCG_REV"
    fetch_source "$NKSR_REPO" "$NKSR_REV" "$nksr_source"
    fetch_source "$PYCG_REPO" "$PYCG_REV" "$pycg_source"
    fetch_source https://github.com/AcademySoftwareFoundation/openvdb.git "$OPENVDB_REV" "$nksr_source/package/external/openvdb"
    fetch_source https://gitlab.com/libeigen/eigen.git "$EIGEN_REV" "$nksr_source/package/external/eigen"
    # Upstream's '3.4' is a moving branch: fix only that build-time checkout.
    "$ENVIRONMENT/bin/python" - "$nksr_source/package/setup.py" "$EIGEN_REV" <<'PY'
from pathlib import Path
import sys
path, revision = Path(sys.argv[1]), sys.argv[2]
text = path.read_text()
old = "git_tag='3.4'"
new = f"git_tag='{revision}'"
if old not in text and new not in text:
    raise SystemExit('Eigen-Checkout im NKSR-Build hat sich geaendert; keine automatische Anpassung.')
path.write_text(text.replace(old, new))
PY
    "$ENVIRONMENT/bin/python" -m pip install --no-build-isolation --no-deps "$pycg_source"
    "$ENVIRONMENT/bin/python" -m pip install --no-build-isolation --no-deps "$nksr_source/package"
}

check_environment() {
    # Match the normal worker: absolute interpreter, no build-time activation.
    env -u LD_LIBRARY_PATH -u CUDA_HOME -u PYTHONPATH \
        PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
        "$ENVIRONMENT/bin/python" "$CHECKER" --smoke --manifest "$MANIFEST" \
        > "$PREFIX/last-smoke.json.tmp" || return $?
    python3 - "$PREFIX/last-smoke.json.tmp" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
assert report.get('ready') is True and report.get('smoke') is True, 'GPU-Test nicht erfolgreich.'
assert [entry['trim'] for entry in report['exports']] == [True, False], 'Meshvergleich fehlt.'
PY
    [[ $? -eq 0 ]] || return 1
    mv -- "$PREFIX/last-smoke.json.tmp" "$PREFIX/last-smoke.json"
}

write_receipt() {
    python3 - "$PREFIX" "$FINGERPRINT" "$ENVIRONMENT/bin/python" "$MANIFEST" <<'PY'
import json, sys
from pathlib import Path
prefix = Path(sys.argv[1])
receipt = {'ready': True, 'fingerprint': sys.argv[2], 'python': sys.argv[3],
           'manifest': json.load(open(sys.argv[4])),
           'smoke': json.loads((prefix / 'last-smoke.json').read_text())}
temporary = prefix / 'receipt.json.tmp'
temporary.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
temporary.replace(prefix / 'receipt.json')
PY
}

main() {
    PREFIX=/opt/scan2mesh
    MANIFEST="$SCRIPT_DIR/../setup/versions.json"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --prefix) [[ $# -ge 2 ]] || die "Wert fuer --prefix fehlt."; PREFIX="$2"; shift 2 ;;
            --manifest) [[ $# -ge 2 ]] || die "Wert fuer --manifest fehlt."; MANIFEST="$2"; shift 2 ;;
            *) die "Unbekannte Option: $1" ;;
        esac
    done
    require_platform
    claim_prefix
    ENVIRONMENT="$PREFIX/envs/nksr"
    # A fresh Ubuntu rootfs may not include Python yet.
    command -v python3 >/dev/null || install_system_packages
    load_manifest
    if receipt_matches; then
        log "Vorhandene passende Installation mit echter GPU-Rekonstruktion pruefen ..."
        check_environment || die "GPU-Pruefung fehlgeschlagen; vorhandene Installation bleibt erhalten."
        log "NKSR ist bereit: $ENVIRONMENT/bin/python"
        return 0
    fi
    install_system_packages
    bootstrap_conda
    install_environment
    build_sources
    check_environment
    write_receipt
    log "NKSR ist bereit: $ENVIRONMENT/bin/python"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
