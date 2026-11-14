from pathlib import Path
import subprocess,tempfile
import yaml
root=Path(__file__).resolve().parent

def render(comp,env='int',extra=None,ok=True):
 cmd=['helm','template',f'monapp-{env}-{comp}',str(root/f'charts/{comp}'),'-n',f'monapp-{"front" if comp=="httpd" else "back"}-{env}','-f',str(root/f'environments/monapp/{env}/{comp}.yaml')]
 with tempfile.NamedTemporaryFile(mode='w',suffix='.yaml') as f:
  yaml.safe_dump(extra or {},f);f.flush()
  r=subprocess.run(cmd+['-f',f.name],capture_output=True,text=True)
 assert (r.returncode==0)==ok,r.stderr
 return [d for d in yaml.safe_load_all(r.stdout) if d] if ok else []

def one(docs,kind):return next(d for d in docs if (d['kind']==kind or (kind=='Deployment' and d['kind']=='StatefulSet')) and not (kind=='Service' and d['spec'].get('clusterIP')=='None'))
for env in ['int','rec','prod']:
 front=render('httpd',env);back=render('springboot',env)
 for comp,docs in [('httpd',front),('springboot',back)]:
  assert len(docs)==(6 if comp=='httpd' else 5)
  expected=f'monapp-{"front" if comp=="httpd" else "back"}-{env}'
  assert {d['metadata']['namespace'] for d in docs}=={expected}
  dep=one(docs,'Deployment');svc=one(docs,'Service')
  assert svc['spec']['selector']==dep['spec']['selector']['matchLabels']==dep['spec']['template']['metadata']['labels']
  app=yaml.safe_load((root/f'argocd/{comp}/monapp-{env}.yaml').read_text())
  assert app['spec']['destination']['namespace']==expected
  assert app['spec']['source']['path']==f'charts/{comp}'
  assert app['spec']['source']['helm']['releaseName']==dep['metadata']['name']
  for f in app['spec']['source']['helm']['valueFiles']:
   assert (root/f'charts/{comp}'/f).resolve().is_file()
 conf=one(front,'ConfigMap')['data']['httpd.conf']
 svc=one(back,'Service')
 stateful=one(back,'Deployment')
 assert stateful['kind']=='StatefulSet' and stateful['spec']['replicas']==2
 assert one(front,'Deployment')['spec']['replicas']==2
 headless=next(d for d in back if d['kind']=='Service' and d['spec'].get('clusterIP')=='None')
 assert stateful['spec']['serviceName']==headless['metadata']['name']
 assert headless['spec']['publishNotReadyAddresses'] is True
 for ordinal in (0,1):
  assert f'http://{stateful["metadata"]["name"]}-{ordinal}.{headless["metadata"]["name"]}.{svc["metadata"]["namespace"]}.svc.cluster.local:8080" route=pod{ordinal}' in conf
 assert 'nofailover=Off' in conf and 'disablereuse=On' in conf
 assert 'HttpOnly; Secure; SameSite=Lax' in conf
 assert 'hcexpr=ready' in conf
 assert 'volumeClaimTemplates' not in stateful['spec']
 peer=one(back,'NetworkPolicy')['spec']['ingress'][0]['from'][0]
 assert peer['namespaceSelector']['matchLabels']['kubernetes.io/metadata.name']==one(front,'Deployment')['metadata']['namespace']
 assert peer['podSelector']['matchLabels']==one(front,'Deployment')['spec']['template']['metadata']['labels']
 assert 'initContainers' not in one(back,'Deployment')['spec']['template']['spec']
 assert 'appdynamics' not in str(front).lower()
 print(f'{env}: déploiements indépendants, Services, DNS, NetworkPolicies et Applications Argo CD OK')
extra=yaml.safe_load((root/'examples/springboot-certificates-appdynamics.yaml').read_text())
docs=render('springboot',extra=extra);spec=one(docs,'Deployment')['spec']['template']['spec'];c=spec['containers'][0]
assert spec['initContainers'][0]['name']=='install-appdynamics'
variables={v['name']:v for v in c['env']}
opts=variables['JAVA_TOOL_OPTIONS']['value']
assert '-javaagent:/opt/appdynamics/javaagent.jar' in opts and '-Djavax.net.ssl.trustStore=' in opts
assert 'secretKeyRef' in variables['APPDYNAMICS_AGENT_ACCOUNT_ACCESS_KEY']['valueFrom']
assert any(v.get('secret',{}).get('secretName')=='monapp-truststore' for v in spec['volumes'])
assert any(m['mountPath']=='/etc/java-truststore' and m['readOnly'] for m in c['volumeMounts'])
assert len(variables)==len(c['env'])
render('springboot',extra={'appdynamics':{'enabled':True}},ok=False)
render('springboot',extra={'env':[{'name':'JAVA_TOOL_OPTIONS','value':'bad'}]},ok=False)
render('springboot',extra={'certificates':[{'name':'tmp','secretName':'x','mountPath':'/x'}]},ok=False)
render('httpd',extra={'port':80},ok=False)
assert not any(x['kind'] in ('Route','NetworkPolicy') for x in render('httpd',extra={'route':{'enabled':False},'networkPolicy':{'enabled':False}}))
print('Certificats + AppDynamics, absence par défaut et validation des erreurs: OK')

plain=render('springboot',extra={'workloadKind':'Deployment'})
assert one(plain,'Deployment')['kind']=='Deployment'
assert not any(d['kind']=='Service' and d['spec'].get('clusterIP')=='None' for d in plain)
plain=render('httpd',extra={'stickySession':{'enabled':False}})
assert 'balancer://springboot' not in one(plain,'ConfigMap')['data']['httpd.conf']
render('httpd',extra={'stickySession':{'cookieName':'bad;cookie'}},ok=False)
render('httpd',extra={'stickySession':{'replicas':1}},ok=False)
print('Sticky: 2x2 pods, routes individuelles, cookie, healthchecks et mode Deployment OK')
