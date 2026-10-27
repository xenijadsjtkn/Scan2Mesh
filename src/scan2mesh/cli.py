"""Headless CLI for reproducible experiments, independent of a web UI."""

import argparse
import json
from pathlib import Path


def add_neural_runtime_arguments(parser, *, timeout=1800.0):
    parser.add_argument("--nksr-python", help="Python executable in the separate NKSR environment; also SCAN2MESH_NKSR_PYTHON")
    parser.add_argument("--nksr-wsl-distro", help="Run that Python inside this WSL distribution; also SCAN2MESH_NKSR_WSL_DISTRO")
    parser.add_argument("--nksr-timeout", type=float, default=timeout, help="Maximum worker runtime in seconds")


def add_neural_reconstruction_arguments(parser):
    add_neural_runtime_arguments(parser)
    parser.add_argument("--nksr-detail-level", type=float, default=0.0, help="0..1: higher preserves more detail and may fit more noise")
    parser.add_argument("--nksr-voxel-size", type=float, help="NKSR reconstruction scale in input units; overrides detail level, distinct from point downsampling")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan2Mesh: inspect and reconstruct registered industrial scan excerpts")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate a synthetic industrial bay in metres")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--seed", type=int, default=7)
    process = commands.add_parser("process", help="Clean, segment and reconstruct a point cloud")
    process.add_argument("input", type=Path)
    process.add_argument("--output", type=Path, required=True)
    process.add_argument("--units", dest="input_units", choices=["m", "mm"], default="m", help="Source coordinate units; NKSR normalizes internally to metres. Length parameters still use source units")
    process.add_argument("--voxel-size", type=float, default=0.0, help="Input units; 0 disables downsampling")
    process.add_argument("--plane-distance", type=float, default=0.01, help="RANSAC inlier distance, in input units")
    process.add_argument("--max-planes", type=int, default=3)
    process.add_argument("--min-plane-points", type=int, default=100)
    process.add_argument("--outlier-neighbors", type=int, default=20)
    process.add_argument("--outlier-std-ratio", type=float, default=2.0)
    process.add_argument("--normal-radius", type=float, help="Input units; default derives from median point spacing")
    process.add_argument("--ball-radius", type=float, help="Override multiscale radii with r and 2r, in input units")
    process.add_argument("--reconstruction", choices=["ball-pivoting", "poisson", "nksr"], default="ball-pivoting", help="NKSR is experimental and requires a separate environment")
    add_neural_reconstruction_arguments(process)
    process.add_argument("--surface-mode", choices=["global", "segmented"], default="global", help="Segmented preview meshes connected planar patches separately")
    process.add_argument("--poisson-depth", type=int, default=8)
    process.add_argument("--crop", type=float, nargs=6, metavar=("XMIN", "YMIN", "ZMIN", "XMAX", "YMAX", "ZMAX"), help="Region in original source coordinates")
    process.add_argument("--seed", type=int, default=7)
    neural_check = commands.add_parser("neural-check", help="Check the separate NKSR installation and GPU without downloading model weights")
    add_neural_runtime_arguments(neural_check, timeout=30.0)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import generate_demo
            result = generate_demo(args.output, args.seed)
        elif args.command == "neural-check":
            from .neural import diagnose_nksr

            result = diagnose_nksr(
                python=args.nksr_python, wsl_distro=args.nksr_wsl_distro,
                timeout=args.nksr_timeout,
            )
        else:
            from .pipeline import PipelineConfig, run_pipeline
            options = vars(args).copy()
            for key in ("command", "input", "output"):
                options.pop(key)
            if options["crop"] is not None:
                options["crop"] = tuple(options["crop"])
            report = run_pipeline(args.input, args.output, PipelineConfig(**options))
            result = {"output": str(args.output), "counts": report["counts"], "quality": report["quality"]}
            if report.get("neural_reconstruction") is not None:
                result["neural_reconstruction"] = report["neural_reconstruction"]
        print(json.dumps(result, indent=2, allow_nan=False))
        if args.command == "neural-check" and not result.get("ready"):
            parser.exit(2)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"scan2mesh: {exc}\n")


if __name__ == "__main__":
    main()
