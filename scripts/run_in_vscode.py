"""VS Code entry point with fresh, non-overwriting output for every run."""

import argparse
import tempfile
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Start a Scan2Mesh demo or process an existing scan")
    parser.add_argument("--input", type=Path, help="Omit to generate a synthetic demo in metres")
    parser.add_argument("--units", choices=["m", "mm"], default="m", help="Coordinate units of the existing scan")
    args = parser.parse_args(argv)
    if args.input is not None and not args.input.is_file():
        parser.error(f"Scan-Datei nicht gefunden: {args.input}")
    if args.input is None and args.units != "m":
        parser.error("Die synthetische Demo verwendet Meter; --units ist nur fuer eigene Scans vorgesehen.")

    from scan2mesh.demo import generate_demo
    from scan2mesh.pipeline import PipelineConfig, run_pipeline

    runs = Path(__file__).resolve().parents[1] / "runs"
    runs.mkdir(exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="vscode-scan-" if args.input else "vscode-demo-", dir=runs))
    if args.input is None:
        source = run_dir / "demo.ply"
        generate_demo(source)
        config = PipelineConfig(voxel_size=0.025, plane_distance=0.015)
    else:
        source = args.input.resolve()
        scale = 1 if args.units == "m" else 1_000
        config = PipelineConfig(voxel_size=0.01 * scale, plane_distance=0.01 * scale)

    result = run_dir / "result"
    print(f"Eingabe: {source}", flush=True)
    print(f"Ausgabe: {result}", flush=True)
    print("Verarbeitung laeuft ...", flush=True)
    report = run_pipeline(source, result, config)
    print(f"Fertig: {report['counts']['mesh_triangles']} Dreiecke")
    print(f"Mesh: {result / 'mesh.ply'}")
    print(f"Qualitaetsbericht: {result / 'report.json'}")
    print("Das Mesh laesst sich in CloudCompare oder MeshLab oeffnen.")
    return result


if __name__ == "__main__":
    main()
