"""Protect reusable chart interfaces and resource identity across the refactor."""

import copy
from pathlib import Path
import shutil
import subprocess
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASE = {
    "httpd": {
        "appName": "app1",
        "environment": "int",
        "clusterName": "hors-prod",
        "route": {"cookieName": "APP1_INT_FRONT"},
    },
    "springboot": {
        "appName": "app1",
        "image": "registry.example.com/equipe/app1:1.0.0",
        "route": {"cookieName": "APP1_INT_BACK"},
    },
}


def render(component, values=None, error=None):
    inputs = copy.deepcopy(BASE[component])
    inputs.update(values or {})
    result = subprocess.run(
        [
            "helm",
            "template",
            "app1-int-" + ("prez" if component == "httpd" else "app"),
            str(ROOT / "charts" / component),
            "-f",
            "-",
        ],
        input=yaml.safe_dump(inputs),
        capture_output=True,
        text=True,
    )
    if error:
        assert result.returncode and error in result.stderr, result.stderr
        return []
    assert result.returncode == 0, result.stderr
    return [d for d in yaml.safe_load_all(result.stdout) if d]


for component in BASE:
    render(component, {"unknownSetting": True}, error="Additional property")
    render(component, {"imagePullPolicy": "Alway"}, error="imagePullPolicy")
    render(
        component,
        {"route": {"cookieName": "COOKIE", "annotations": {"x": "y"}}},
        error="Additional property",
    )
    render(component, {"replicas": 0}, error="replicas")
    docs = render(component)
    deploy = next(d for d in docs if d["kind"] == "Deployment")
    service = next(d for d in docs if d["kind"] == "Service")
    assert deploy["spec"]["selector"]["matchLabels"] == service["spec"]["selector"]
    assert "helm.sh/chart" not in deploy["spec"]["selector"]["matchLabels"]
    assert deploy["metadata"]["labels"]["app.kubernetes.io/component"] == component
    assert deploy["spec"]["template"]["spec"]["automountServiceAccountToken"] is False

render("springboot", {"image": ""}, error="image")
render("springboot", {"env": [{"name": "NUMBER", "value": 1}]}, error="value")
render(
    "springboot",
    {"extraVolumeMounts": [{"name": "missing", "mountPath": "/data"}]},
    error="volume absent",
)
render(
    "springboot",
    {"certificates": [{"name": "cert", "secretName": "cert", "mountPath": "/tmp"}]},
    error="montage",
)
render(
    "httpd",
    {"networkPolicy": {"enabled": False, "egress": {"enabled": True}}},
    error="networkPolicy.enabled",
)
render("httpd", {"appName": "a" * 30}, error="hostname calcule")
custom = render(
    "httpd", {"readinessProbe": {"tcpSocket": {"port": "http"}, "periodSeconds": 9}}
)
assert (
    next(d for d in custom if d["kind"] == "Deployment")["spec"]["template"]["spec"][
        "containers"
    ][0]["readinessProbe"]["periodSeconds"]
    == 9
)
render(
    "httpd",
    {"readinessProbe": {"tcpSocket": {"port": "http"}, "exec": {"command": ["true"]}}},
    error="oneOf",
)

# Two dependencies render in one Helm namespace, exposing collisions between named helpers.
# This is a composition test, not our front/back deployment topology.
with tempfile.TemporaryDirectory() as tmp:
    parent = Path(tmp)
    (parent / "charts").mkdir()
    (parent / "Chart.yaml").write_text(
        "apiVersion: v2\nname: composition-test\nversion: 0.1.0\n"
    )
    values = {}
    for component in BASE:
        shutil.copytree(ROOT / "charts" / component, parent / "charts" / component)
        values[component] = dict(BASE[component], fullnameOverride="test-" + component)
    (parent / "values.yaml").write_text(yaml.safe_dump(values))
    r = subprocess.run(
        ["helm", "template", "composition", str(parent)], capture_output=True, text=True
    )
    assert r.returncode == 0, r.stderr
    docs = [d for d in yaml.safe_load_all(r.stdout) if d]
    deployments = [d for d in docs if d["kind"] == "Deployment"]
    assert {d["metadata"]["name"] for d in deployments} == {
        "test-httpd",
        "test-springboot",
    }
    for d in deployments:
        component = d["metadata"]["name"].removeprefix("test-")
        assert (
            d["spec"]["selector"]["matchLabels"]["app.kubernetes.io/component"]
            == component
        )
print(
    "Chart contracts: strict values, required image, volumes, probes, stable selectors and helper isolation OK"
)
