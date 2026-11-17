from pathlib import Path
import subprocess, tempfile
import yaml

root = Path(__file__).resolve().parents[1]


def render(comp, env="int", extra=None, ok=True):
    cmd = [
        "helm",
        "template",
        f"monapp-{env}-{comp}",
        str(root / f"charts/{comp}"),
        "-n",
        f'monapp-{"front" if comp=="httpd" else "back"}-{env}',
        "-f",
        str(root / f"environments/monapp/{env}/{comp}.yaml"),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml") as f:
        yaml.safe_dump(extra or {}, f)
        f.flush()
        r = subprocess.run(cmd + ["-f", f.name], capture_output=True, text=True)
    assert (r.returncode == 0) == ok, r.stderr
    return [d for d in yaml.safe_load_all(r.stdout) if d] if ok else []


def one(docs, kind):
    return next(d for d in docs if d["kind"] == kind)


for env in ["int", "rec", "prod"]:
    front = render("httpd", env)
    back = render("springboot", env)
    for comp, docs in [("httpd", front), ("springboot", back)]:
        assert len(docs) == (6 if comp == "httpd" else 5)
        expected = f'monapp-{"front" if comp=="httpd" else "back"}-{env}'
        assert {d["metadata"]["namespace"] for d in docs} == {expected}
        dep = one(docs, "Deployment")
        svc = one(docs, "Service")
        assert (
            svc["spec"]["selector"]
            == dep["spec"]["selector"]["matchLabels"]
            == dep["spec"]["template"]["metadata"]["labels"]
        )
        app = yaml.safe_load((root / f"argocd/{comp}/monapp-{env}.yaml").read_text())
        assert app["spec"]["destination"]["namespace"] == expected
        assert app["spec"]["source"]["path"] == f"charts/{comp}"
        assert app["spec"]["source"]["helm"]["releaseName"] == dep["metadata"]["name"]
        for f in app["spec"]["source"]["helm"]["valueFiles"]:
            assert (root / f"charts/{comp}" / f).resolve().is_file()
    conf = one(front, "ConfigMap")["data"]["httpd.conf"]
    svc = one(back, "Service")
    assert one(back, "Deployment")["spec"]["replicas"] == 2
    assert one(front, "Deployment")["spec"]["replicas"] == 2
    assert not any(
        d["kind"] == "StatefulSet" or d.get("spec", {}).get("clusterIP") == "None"
        for d in back
    )
    route = one(back, "Route")
    fr = one(front, "Route")
    assert route["spec"]["to"]["name"] == svc["metadata"]["name"]
    assert f'https://{route["spec"]["host"]}/' in conf
    assert "ProxyPreserveHost Off" in conf and "SSLProxyVerify require" in conf
    assert "SSLProxyCheckPeerName On" in conf
    assert f'RequestHeader set X-Forwarded-Host "{fr["spec"]["host"]}"' in conf
    assert "ProxyPassReverseCookieDomain" in conf
    assert "balancer://" not in conf and "BalancerMember" not in conf
    cookiekey = "router.openshift.io/cookie_name"
    assert (
        fr["metadata"]["annotations"][cookiekey]
        != route["metadata"]["annotations"][cookiekey]
    )
    assert (
        route["metadata"]["annotations"]["haproxy.router.openshift.io/disable_cookies"]
        == "false"
    )
    assert route["metadata"]["labels"]["ingress-scope"] == "internal"
    peer = one(back, "NetworkPolicy")["spec"]["ingress"][0]["from"][0]
    assert (
        peer["namespaceSelector"]["matchLabels"]["network.openshift.io/policy-group"]
        == "ingress"
    )
    assert peer["podSelector"] == {}
    assert "initContainers" not in one(back, "Deployment")["spec"]["template"]["spec"]
    assert "appdynamics" not in str(front).lower()
    print(
        f"{env}: déploiements indépendants, Services, DNS, NetworkPolicies et Applications Argo CD OK"
    )
extra = yaml.safe_load(
    (root / "examples/springboot-certificates-appdynamics.yaml").read_text()
)
docs = render("springboot", extra=extra)
spec = one(docs, "Deployment")["spec"]["template"]["spec"]
c = spec["containers"][0]
assert spec["initContainers"][0]["name"] == "install-appdynamics"
variables = {v["name"]: v for v in c["env"]}
opts = variables["JAVA_TOOL_OPTIONS"]["value"]
assert (
    "-javaagent:/opt/appdynamics/javaagent.jar" in opts
    and "-Djavax.net.ssl.trustStore=" in opts
)
assert "secretKeyRef" in variables["APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY"]["valueFrom"]
assert any(
    v.get("secret", {}).get("secretName") == "monapp-truststore"
    for v in spec["volumes"]
)
assert any(
    m["mountPath"] == "/etc/java-truststore" and m["readOnly"]
    for m in c["volumeMounts"]
)
assert len(variables) == len(c["env"])
render("springboot", extra={"appdynamics": {"enabled": True}}, ok=False)
render(
    "springboot",
    extra={"env": [{"name": "JAVA_TOOL_OPTIONS", "value": "bad"}]},
    ok=False,
)
render(
    "springboot",
    extra={"certificates": [{"name": "tmp", "secretName": "x", "mountPath": "/x"}]},
    ok=False,
)
render("httpd", extra={"port": 80}, ok=False)
assert not any(
    x["kind"] in ("Route", "NetworkPolicy")
    for x in render(
        "httpd",
        extra={"route": {"enabled": False}, "networkPolicy": {"enabled": False}},
    )
)
print("Certificats + AppDynamics, absence par défaut et validation des erreurs: OK")

render("springboot", extra={"workloadKind": "StatefulSet"}, ok=False)
render("httpd", extra={"stickySession": {"enabled": True}}, ok=False)
render(
    "httpd", extra={"backendRoute": {"host": "monapp-int.apps.example.com"}}, ok=False
)
render("springboot", extra={"route": {"cookieName": "bad;cookie"}}, ok=False)
ca = render(
    "httpd",
    extra={"backendRoute": {"caSecretName": "router-ca", "caSecretKey": "root.pem"}},
)
spec = one(ca, "Deployment")["spec"]["template"]["spec"]
volume = next(v for v in spec["volumes"] if v["name"] == "backend-route-ca")
assert volume["secret"]["secretName"] == "router-ca"
assert volume["secret"]["items"] == [{"key": "root.pem", "path": "ca.crt"}]
assert (
    "SSLProxyCACertificateFile /etc/backend-route-ca/ca.crt"
    in one(ca, "ConfigMap")["data"]["httpd.conf"]
)
assert not any(
    d["kind"] == "Route"
    for d in render("springboot", extra={"route": {"enabled": False}})
)
print(
    "Routes frontend/backend, cookies distincts, TLS vérifié, CA montée, anciens paramètres rejetés: OK"
)

for env in ("int", "rec", "prod"):
    spec = one(render("httpd", env), "Deployment")["spec"]["template"]["spec"]
    c = spec["containers"][0]
    assert c["image"] == "registry.access.redhat.com/hi/httpd:latest"
    assert c["command"] == ["/usr/bin/httpd"]
    assert c["args"] == ["-f", "/etc/custom-httpd/httpd.conf", "-DFOREGROUND"]
    assert c["securityContext"]["readOnlyRootFilesystem"] is True
    assert "runAsUser" not in spec["securityContext"]
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        assert "tcpSocket" in c[probe] and "exec" not in c[probe]
print("Image Red Hat hi/httpd runtime, démarrage sans shell et probes TCP: OK")

# Preferred standalone Applications for users creating objects through the Argo CD UI.
from support import render_application

for path in sorted((root / "examples/applications").glob("*.yaml")):
    app = yaml.safe_load(path.read_text())
    _, manifest = render_application(app)
    docs = [doc for doc in yaml.safe_load_all(manifest) if doc]
    assert {doc["metadata"]["namespace"] for doc in docs} == {
        app["spec"]["destination"]["namespace"]
    }
    assert one(docs, "Deployment")["metadata"]["name"] == app["metadata"]["name"]
print("Standalone Application examples: helm lint and helm template OK")
