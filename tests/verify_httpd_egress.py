"""Offline tests with documentation-only IPv4 addresses; never deployed."""
from pathlib import Path
import subprocess
import yaml

root=Path(__file__).resolve().parents[1]
base=['helm','template','app1-int-prez',str(root/'charts/httpd'),'--namespace','app1-intfr','--set','clusterName=hors-prod,environment=int,appName=app1,route.cookieName=APP1_INT_FRONT']

def render(egress, ok=True):
    result=subprocess.run(base+['-f','-'],input=yaml.safe_dump({'networkPolicy':{'egress':egress}}),capture_output=True,text=True)
    assert (result.returncode==0)==ok, result.stderr
    if not ok:return
    return next(d for d in yaml.safe_load_all(result.stdout) if d and d['kind']=='NetworkPolicy')

default=render({'enabled':False})
assert default['spec']['policyTypes']==['Ingress'] and 'egress' not in default['spec']
for port in [53,5353]:
    spec=render({'enabled':True,'backendRouteIPs':['192.0.2.11','192.0.2.12'],'dnsIPs':['192.0.2.53'],'dnsPort':port})['spec']
    assert spec['ingress']==default['spec']['ingress']
    assert spec['policyTypes']==['Ingress','Egress']
    https,dns=spec['egress']
    assert https['to']==[{'ipBlock':{'cidr':ip+'/32'}} for ip in ['192.0.2.11','192.0.2.12']]
    assert https['ports']==[{'protocol':'TCP','port':443}]
    assert dns['to']==[{'ipBlock':{'cidr':'192.0.2.53/32'}}]
    assert dns['ports']==[{'protocol':proto,'port':port} for proto in ['UDP','TCP']]
render({'enabled':True},ok=False)
render({'enabled':True,'backendRouteIPs':['192.0.2.11']},ok=False)
render({'enabled':True,'backendRouteIPs':['999.0.0.1'],'dnsIPs':['192.0.2.53']},ok=False)
print('Egress HTTPD: activation, deux IP /32, DNS TCP/UDP 53 et 5353, ingress conserve et erreurs de configuration OK')
