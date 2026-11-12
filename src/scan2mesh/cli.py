"""All reconstruction entry points use the same reference NKSR workflow."""

import argparse
from pathlib import Path


def main(argv=None):
    import sys
    from .desktop import main as run

    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "process":
        parser = argparse.ArgumentParser(description="NKSR direkt: Originalpunkte, Detail 1.0 und beide Exporte")
        parser.add_argument("input", type=Path)
        parser.add_argument("--output-root", "--output", type=Path, help="Stammverzeichnis; jeder Lauf erzeugt einen neuen nksr-direkt-Unterordner")
        parser.add_argument("--units", choices=("m", "mm"), default="m")
        parser.add_argument("--nksr-python")
        parser.add_argument("--nksr-wsl-distro")
        args = parser.parse_args(arguments[1:])
        forwarded = ["--input", str(args.input), "--units", args.units]
        for name in ("output_root", "nksr_python", "nksr_wsl_distro"):
            if getattr(args, name) is not None:
                forwarded.extend(["--" + name.replace("_", "-"), str(getattr(args, name))])
        run(forwarded)
    else:
        run(arguments)


if __name__ == "__main__":
    main()
