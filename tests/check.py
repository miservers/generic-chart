"""Single offline check command; never contacts a Kubernetes cluster."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build/rendered")
    args = parser.parse_args()
    for binary in ["helm", "go"]:
        if not shutil.which(binary):
            parser.error(f"{binary} is required in PATH (Helm 3 and Go compiler)")
    commands = [
        ["render_clusters.py", "--output", str(args.output.resolve())],
        ["verify_examples.py"],
        ["verify_route_options.py"],
        ["verify_httpd_egress.py"],
        ["verify_chart_contracts.py"],
    ]
    for script, *options in commands:
        subprocess.run(
            [sys.executable, str(ROOT / "tests" / script), *options], check=True
        )
    print(
        "All offline checks passed. Cluster connectivity and Route affinity remain untested."
    )


if __name__ == "__main__":
    main()
