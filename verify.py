from pathlib import Path
import subprocess
import yaml

root = Path(__file__).resolve().parent
chart = str(root / 'charts/spring-httpd')
def render(release, *args, ok=True):
    r = subprocess.run(['helm', 'template', release, chart, *args], capture_output=True, text=True)
    assert (r.returncode == 0) == ok, r.stderr
    return [d for d in yaml.safe_load_all(r.stdout) if d] if ok else []

for env in ('int', 'rec', 'prod'):
    release = f'monapp-{env}'
    docs = render(release, '-f', str(root / f'environments/monapp/{env}.yaml'))
    assert len(docs) == 10
    assert {d['metadata']['namespace'] for d in docs} == {f'monapp-front-{env}', f'monapp-back-{env}'}
    for c in ('frontend', 'backend'):
        deploy = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == f'{release}-{c}')
        svc = next(d for d in docs if d['kind'] == 'Service' and d['metadata']['name'] == f'{release}-{c}')
        assert svc['spec']['selector'] == deploy['spec']['selector']['matchLabels'] == deploy['spec']['template']['metadata']['labels']
    conf = next(d for d in docs if d['kind'] == 'ConfigMap')['data']['httpd.conf']
    assert f'http://{release}-backend.monapp-back-{env}.svc.cluster.local:8080/' in conf
    policy = next(d for d in docs if d['kind'] == 'NetworkPolicy' and d['metadata']['name'].endswith('-backend'))
    peers = policy['spec']['ingress'][0]['from']
    assert len(peers) == 1 and 'namespaceSelector' in peers[0] and 'podSelector' in peers[0]
    assert peers[0]['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name'] == f'monapp-front-{env}'
    print(f'{env}: 10 ressources, namespaces, selectors et cible DNS OK')
render('invalid', '--set', 'namespaces.backend=monapp-front-int', ok=False)
render('invalid', '--set', 'frontend.port=80', ok=False)
docs = render('options', '--set', 'route.enabled=false,networkPolicy.enabled=false')
assert not any(d['kind'] in ('Route', 'NetworkPolicy') for d in docs)
print('Rejets et options: OK')
