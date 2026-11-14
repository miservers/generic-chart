"""Test local : 2 Apache réels + 2 backends HTTP simulés. Pas un test OpenShift.
APACHE_BIN et APACHE_MODULES désignent une installation Apache 2.4 avec hcheck.
Nécessite Helm dans PATH et PyYAML. Ports locaux 18080/18081 et 19080/19081.
"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import os,pwd,grp,re,subprocess,tempfile,time,urllib.request,urllib.error
import yaml
root=Path(__file__).resolve().parents[1]
apache=os.environ['APACHE_BIN'];modules=os.environ['APACHE_MODULES']
compiled=subprocess.check_output([apache,'-l'],text=True)
r=subprocess.check_output(['helm','template','monapp-int-httpd',str(root/'charts/httpd'),'-n','monapp-front-int','-f',str(root/'environments/monapp/int/httpd.yaml')],text=True)
config=next(d for d in yaml.safe_load_all(r) if d and d['kind']=='ConfigMap')['data']['httpd.conf']
servers=[];processes=[];logs=[];healthy=[True,True]
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  idx=self.server.idx
  code=200 if not self.path.startswith('/actuator') or healthy[idx] else 503
  body=f'pod{idx}'.encode();self.send_response(code);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass

def request(port,cookie=None):
 req=urllib.request.Request(f'http://127.0.0.1:{port}/',headers={'Cookie':cookie} if cookie else {})
 with urllib.request.urlopen(req,timeout=4) as res:
  return res.read().decode(),res.headers.get('Set-Cookie')

def wait_request(port,cookie=None):
 end=time.monotonic()+20
 while time.monotonic()<end:
  try:return request(port,cookie)
  except (OSError,urllib.error.URLError):time.sleep(.2)
 raise AssertionError('Apache non disponible')
with tempfile.TemporaryDirectory(prefix='sticky-test-') as tmp:
 try:
  for i in range(2):
   srv=ThreadingHTTPServer(('127.0.0.1',19080+i),Handler);srv.idx=i;servers.append(srv)
   Thread(target=srv.serve_forever,daemon=True).start()
  for i in range(2):
   d=Path(tmp)/str(i);d.mkdir()
   s=config.replace('ServerRoot "/etc/httpd"',f'ServerRoot "{d}"').replace('Listen 8080',f'Listen 127.0.0.1:{18080+i}').replace('/run/httpd',str(d)).replace('User apache',f'User {pwd.getpwuid(os.getuid()).pw_name}').replace('Group apache',f'Group {grp.getgrgid(os.getgid()).gr_name}')
   for j in range(2):
    s=s.replace(f'monapp-int-springboot-{j}.monapp-int-springboot-headless.monapp-back-int.svc.cluster.local:8080',f'127.0.0.1:{19080+j}')
   # Certains modules sont statiques dans Debian et dynamiques dans UBI.
   s='\n'.join(line for line in s.splitlines() if not (line.strip().startswith('LoadModule') and (Path(line.split()[-1]).stem+'.c') in compiled))
   s=s.replace('modules/',modules.rstrip('/')+'/')
   f=d/'httpd.conf';f.write_text(s+'\n')
   subprocess.run([apache,'-t','-f',str(f)],check=True,capture_output=True)
   log=open(d/'output.log','w+');logs.append(log)
   processes.append(subprocess.Popen([apache,'-f',str(f),'-DFOREGROUND'],stdout=log,stderr=log))
  first,header=wait_request(18080);cookie=header.split(';')[0]
  assert cookie.endswith('.'+first),(cookie,first)
  assert all(x in header for x in ('HttpOnly','Secure','SameSite=Lax'))
  for i in range(10):assert wait_request(18080+i%2,cookie)[0]==first
  print('PASS: affinité conservée sur les deux HTTPD',flush=True)
  failed=int(first[-1]);healthy[failed]=False
  end=time.monotonic()+18
  while time.monotonic()<end:
   body,header=wait_request(18081,cookie)
   if body!=first:break
   time.sleep(.3)
  assert body!=first and header,(body,header)
  cookie=header.split(';')[0]
  assert cookie.endswith('.'+body)
  for i in range(6):assert wait_request(18080+i%2,cookie)[0]==body
  print('PASS: readiness 503 => bascule et nouveau cookie sur les deux HTTPD',flush=True)
  healthy[failed]=True;time.sleep(6)
  for i in range(6):assert wait_request(18080+i%2,cookie)[0]==body
  print('PASS: le retour du backend ne déplace pas la session existante',flush=True)
  active=int(body[-1]);servers[active].shutdown();servers[active].server_close()
  end=time.monotonic()+18
  while time.monotonic()<end:
   try:
    final,newheader=request(18080,cookie)
    if final!=body:break
   except (OSError,urllib.error.URLError):pass
   time.sleep(.3)
  assert final!=body and newheader
  cookie=newheader.split(';')[0]
  processes[0].terminate();processes[0].wait(timeout=5)
  assert wait_request(18081,cookie)[0]==final
  print('PASS: arrêt backend => bascule ; arrêt HTTPD => affinité conservée via le second',flush=True)
 except Exception:
  for log in logs:
   log.flush();log.seek(0);print(log.read()[-6000:])
  raise
 finally:
  for proc in processes:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
  for srv in servers:srv.shutdown();srv.server_close()
  for log in logs:log.close()
