"""Check conditional cookie requirements and backend host assignment without a cluster."""

from pathlib import Path
import subprocess
import yaml

root = Path(__file__).resolve().parents[1]


def render(component, values, error=None):
    r = subprocess.run(
        [
            "helm",
            "template",
            "app1-int-" + ("prez" if component == "httpd" else "app"),
            str(root / "charts" / component),
            "-n",
            "app1-int" + ("fr" if component == "httpd" else ""),
            "-f",
            "-",
        ],
        input=yaml.safe_dump(values),
        capture_output=True,
        text=True,
    )
    if error:
        assert r.returncode != 0 and error in r.stderr, r.stderr
        return []
    assert r.returncode == 0, r.stderr
    return [d for d in yaml.safe_load_all(r.stdout) if d]


for component in ["httpd", "springboot"]:
    base = {"appName": "app1"}
    if component == "springboot":
        base["image"] = "registry.example.com/equipe/app1:1.0.0"
    if component == "httpd":
        base.update(clusterName="hors-prod", environment="int")
    render(component, base, error="route.cookieName est requis")
    docs = render(component, dict(base, route={"enabled": False}))
    assert not any(d["kind"] == "Route" for d in docs)
    docs = render(component, dict(base, session="disabled"))
    route = next(d for d in docs if d["kind"] == "Route")
    assert (
        route["metadata"]["annotations"]["haproxy.router.openshift.io/disable_cookies"]
        == "true"
    )
    assert "router.openshift.io/cookie_name" not in route["metadata"]["annotations"]
    docs = render(component, dict(base, route={"cookieName": "APP1_INT_TEST"}))
    route = next(d for d in docs if d["kind"] == "Route")
    assert (
        route["metadata"]["annotations"]["router.openshift.io/cookie_name"]
        == "APP1_INT_TEST"
    )
    if component == "springboot":
        assert "host" not in route["spec"]
    docs = render(
        component,
        dict(
            base, route={"cookieName": "APP1_INT_TEST", "host": "explicit.example.com"}
        ),
    )
    assert (
        next(d for d in docs if d["kind"] == "Route")["spec"]["host"]
        == "explicit.example.com"
    )
    render(component, dict(base, appName="", session="disabled"), error="appName")
print(
    "Routes: cookies conditionnels, absence de Route, hostname backend omis, hosts explicites et appName requis OK"
)
