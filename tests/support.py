"""Shared subprocess and Argo CD-to-Helm argument handling for offline checks."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise RuntimeError(f"Command failed: {args}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def helm_arguments(application):
    spec = application["spec"]
    source = spec["source"]
    chart = ROOT / source["path"]
    helm = source["helm"]
    options = ["--namespace", spec["destination"]["namespace"]]
    for filename in helm.get("valueFiles", []):
        path = (chart / filename).resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        options += ["-f", str(path)]
    for param in helm.get("parameters", []):
        flag = "--set-string" if param.get("forceString", False) else "--set"
        options += [flag, param["name"] + "=" + param["value"]]
    return str(chart), helm.get("releaseName", application["metadata"]["name"]), options


def render_application(application):
    chart, release, options = helm_arguments(application)
    lint = run(["helm", "lint", chart, *options])
    manifests = run(["helm", "template", release, chart, *options])
    return lint, manifests
