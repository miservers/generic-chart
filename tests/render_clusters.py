"""Render the checked-in List/Matrix templates offline, then lint/template every Application.
Requires Python + PyYAML, Go and Helm 3. This is not an Argo CD controller integration test.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]

def run(args, **kw):
    result = subprocess.run(args, text=True, capture_output=True, **kw)
    if result.returncode:
        raise RuntimeError(f'Command failed: {args}\n{result.stdout}\n{result.stderr}')
    return result.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    out = parser.parse_args().output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        helper = str(Path(tmp)/'render-go')
        run(['go', 'build', '-o', helper, str(ROOT/'tests/render_go_template.go')])
        def render(value, data):
            return json.loads(run([helper], input=json.dumps({'value':value, 'data':data})))
        for source in sorted((ROOT/'argocd/clusters').glob('*/applicationset.yaml')):
            appset = yaml.safe_load(source.read_text())
            generators = appset['spec']['generators'][0]['matrix']['generators']
            constants, = generators[0]['list']['elements']
            cluster = constants['clusterName']
            assert 'routesDomain' not in source.read_text()
            assert 'baseDomain' not in source.read_text()
            assert source.read_text().count('clusterName:') == 1
            combinations = yaml.safe_load(render(generators[1]['list']['elementsYaml'], constants))
            expected = {(a,e,c) for a in constants['apps'] for e in constants['envs'] for c in constants['components']}
            assert {(x['app'],x['env'],x['component']) for x in combinations} == expected
            assert len(combinations) == len(expected)
            apps, routes, proxy_configs = [], {}, {}
            cluster_out = out/cluster
            cluster_out.mkdir(exist_ok=True)
            for item in combinations:
                app = render(appset['spec']['template'], dict(constants, **item))
                app = {'apiVersion':'argoproj.io/v1alpha1', 'kind':'Application', **app}
                app['metadata']['namespace'] = appset['metadata']['namespace']
                spec = app['spec']; helm = spec['source']['helm']; comp = item['component']
                suffix = 'prez' if comp == 'httpd' else 'app'
                name = f"{item['app']}-{item['env']}-{suffix}"
                ns = f"{item['app']}-{item['env']}" + ('fr' if comp=='httpd' else '')
                assert app['metadata']['name'] == helm['releaseName'] == name
                assert spec['destination'] == {'server':'https://kubernetes.default.svc', 'namespace':ns}
                assert app['metadata']['labels']['deployment.example.com/cluster'] == cluster
                chart = ROOT/spec['source']['path']; options = []
                for filename in helm['valueFiles']:
                    path = (chart/filename).resolve()
                    assert path.is_file()
                    assert not {'routesDomain','baseDomain','clusterName'} & yaml.safe_load(path.read_text()).keys()
                    options += ['-f', str(path)]
                for param in helm['parameters']:
                    options += ['--set-string', param['name']+'='+param['value']] if param['name']!='replicas' else ['--set', 'replicas='+param['value']]
                lint = run(['helm','lint',str(chart),'--namespace',ns,*options])
                output = run(['helm','template',name,str(chart),'--namespace',ns,*options])
                docs = [d for d in yaml.safe_load_all(output) if d]
                route = next(d for d in docs if d['kind']=='Route')
                assert yaml.safe_load((chart/'values.yaml').read_text())['baseDomain'] == 'example.com'
                assert {p['name']:p['value'] for p in helm['parameters']}['clusterName'] == cluster
                host = f"{name}-{ns}.apps.{cluster}.example.com"
                assert len(host)<=253
                if comp == 'springboot':
                    assert 'host' not in route['spec'], 'Backend host must be assigned by OpenShift'
                else:
                    assert route['spec']['host'] == host
                assert next(d for d in docs if d['kind']=='Deployment')['spec']['replicas']==2
                routes[item['app'],item['env'],comp]=host
                if comp=='httpd':
                    conf=next(d for d in docs if d['kind']=='ConfigMap')['data']['httpd.conf']
                    proxy_configs[item['app'],item['env']]=conf
                    assert f'ServerName https://{host}:443' in conf
                (cluster_out/(name+'.yaml')).write_text(output)
                (cluster_out/(name+'.lint.txt')).write_text(lint)
                apps.append(app)
                rows.append({'cluster':cluster,'application':name,'namespace':ns,'expectedRouteHost':host,'renderedRouteHost':route['spec'].get('host'),'lint':'PASS','template':'PASS'})
            for (a,e),conf in proxy_configs.items():
                backend=routes[a,e,'springboot']
                assert f'ProxyPass "/" "https://{backend}/"' in conf
                assert f'ProxyPassReverse "/" "https://{backend}/"' in conf
                assert f'ProxyPassReverseCookieDomain "{backend}"' in conf
            (cluster_out/'applications.yaml').write_text(yaml.safe_dump_all(apps,sort_keys=False))
            print(f'{cluster}: {len(apps)} Applications, helm lint + helm template OK')
    # HTTPD still needs a cluster to compute its expected target; Spring Boot does not.
    cmd = ['helm', 'template', 'test', str(ROOT/'charts/httpd'), '--set',
           'appName=app1,environment=int,route.cookieName=APP1_INT_FRONT']
    result = subprocess.run(cmd, text=True, capture_output=True)
    assert result.returncode != 0 and 'clusterName requis' in result.stderr
    assert len(rows)==16
    (out/'report.json').write_text(json.dumps(rows,indent=2)+'\n')
    print('16/16 rendus valides ; noms, labels, destinations et hosts attendus HTTPD verifies ; host reel backend non lu.')

if __name__=='__main__':main()
