"""Headless CLI for reproducible experiments, independent of a web UI."""

import argparse
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan2Mesh: inspect and reconstruct registered industrial scan excerpts")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate a synthetic industrial bay in metres")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--seed", type=int, default=7)
    process = commands.add_parser("process", help="Clean, segment and reconstruct a point cloud")
    process.add_argument("input", type=Path)
    process.add_argument("--output", type=Path, required=True)
    process.add_argument("--voxel-size", type=float, default=0.0, help="Input units; 0 disables downsampling")
    process.add_argument("--plane-distance", type=float, default=0.01, help="RANSAC inlier distance, in input units")
    process.add_argument("--max-planes", type=int, default=3)
    process.add_argument("--min-plane-points", type=int, default=100)
    process.add_argument("--outlier-neighbors", type=int, default=20)
    process.add_argument("--outlier-std-ratio", type=float, default=2.0)
    process.add_argument("--normal-radius", type=float, help="Input units; default derives from median point spacing")
    process.add_argument("--ball-radius", type=float, help="Override multiscale radii with r and 2r, in input units")
    process.add_argument("--reconstruction", choices=["ball-pivoting", "poisson"], default="ball-pivoting")
    process.add_argument("--surface-mode", choices=["global", "segmented"], default="global", help="Segmented preview meshes connected planar patches separately")
    process.add_argument("--poisson-depth", type=int, default=8)
    process.add_argument("--crop", type=float, nargs=6, metavar=("XMIN", "YMIN", "ZMIN", "XMAX", "YMAX", "ZMAX"), help="Region in original source coordinates")
    process.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            from .demo import generate_demo
            result = generate_demo(args.output, args.seed)
        else:
            from .pipeline import PipelineConfig, run_pipeline
            options = vars(args).copy()
            for key in ("command", "input", "output"):
                options.pop(key)
            if options["crop"] is not None:
                options["crop"] = tuple(options["crop"])
            report = run_pipeline(args.input, args.output, PipelineConfig(**options))
            result = {"output": str(args.output), "counts": report["counts"], "quality": report["quality"]}
        print(json.dumps(result, indent=2, allow_nan=False))
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"scan2mesh: {exc}\n")


if __name__ == "__main__":
    main()
