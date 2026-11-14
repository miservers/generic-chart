"""Deux Apache réels vers un serveur HTTPS simulant l'interface d'une Route.
Valide le proxy, pas l'algorithme d'affinité du routeur OpenShift.
APACHE_BIN, APACHE_MODULES, Helm, OpenSSL et PyYAML requis.
"""
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from threading import Thread
import os,pwd,grp,subprocess,tempfile,time,urllib.request,urllib.error,ssl,json
import yaml
root=Path(__file__).resolve().parents[1]
apache=os.environ['APACHE_BIN'];modules=os.environ['APACHE_MODULES']
compiled=subprocess.check_output([apache,'-l'],text=True)
r=subprocess.check_output(['helm','template','monapp-int-httpd',str(root/'charts/httpd'),'-n','monapp-front-int','-f',str(root/'environments/monapp/int/httpd.yaml')],text=True)
conf=next(d for d in yaml.safe_load_all(r) if d and d['kind']=='ConfigMap')['data']['httpd.conf']
processes=[];logs=[];sni=[];server=None
class Handler(BaseHTTPRequestHandler):
 def handle(self):
  try:super().handle()
  except (BrokenPipeError,ConnectionResetError):pass  # fermeture TLS attendue lors du test négatif
 def do_GET(self):
  self.send_response(200)
  self.send_header('Set-Cookie','MONAPP_INT_BACK=endpoint-1; Path=/; HttpOnly; Secure')
  self.send_header('Set-Cookie','JSESSIONID=test; Domain=localhost; Path=/; Secure')
  self.send_header('Location','https://localhost:19443/login')
  body=json.dumps(dict(self.headers)).encode();self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*args):pass

def request(port):
 req=urllib.request.Request(f'http://127.0.0.1:{port}/',headers={'Host':'monapp-int.apps.example.com','Cookie':'MONAPP_INT_FRONT=f1; MONAPP_INT_BACK=endpoint-1; JSESSIONID=test','X-Forwarded-Host':'attacker.invalid','Forwarded':'host=attacker.invalid'})
 with urllib.request.urlopen(req,timeout=4) as r:return json.loads(r.read()),r.headers

with tempfile.TemporaryDirectory(prefix='route-test-') as tmp:
 try:
  t=Path(tmp)
  subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(t/'key.pem'),'-out',str(t/'cert.pem'),'-days','1','-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],check=True,capture_output=True)
  server=ThreadingHTTPServer(('127.0.0.1',19443),Handler)
  ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(t/'cert.pem',t/'key.pem')
  ctx.set_servername_callback(lambda sock,name,context:sni.append(name))
  server.socket=ctx.wrap_socket(server.socket,server_side=True)
  Thread(target=server.serve_forever,daemon=True).start()
  for i in range(3):
   d=t/str(i);d.mkdir()
   # Le troisième proxy utilise une IP absente des SAN du certificat : doit échouer.
   host='localhost' if i<2 else '127.0.0.1'
   s=conf.replace('ServerRoot "/etc/httpd"',f'ServerRoot "{d}"').replace('Listen 8080',f'Listen 127.0.0.1:{18080+i}').replace('/run/httpd',str(d)).replace('User apache',f'User {pwd.getpwuid(os.getuid()).pw_name}').replace('Group apache',f'Group {grp.getgrgid(os.getgid()).gr_name}')
   s=s.replace('https://monapp-back-int.apps-internal.example.com/',f'https://{host}:19443/').replace('"monapp-back-int.apps-internal.example.com"','"localhost"')
   s=s.replace('/etc/pki/tls/certs/ca-bundle.crt',str(t/'cert.pem'))
   s='\n'.join(line for line in s.splitlines() if not (line.strip().startswith('LoadModule') and (Path(line.split()[-1]).stem+'.c') in compiled))
   s=s.replace('modules/',modules.rstrip('/')+'/')
   f=d/'httpd.conf';f.write_text(s+'\n');subprocess.run([apache,'-t','-f',str(f)],check=True,capture_output=True)
   log=open(d/'output.log','w+');logs.append(log);processes.append(subprocess.Popen([apache,'-f',str(f),'-DFOREGROUND'],stdout=log,stderr=log))
  for port in (18080,18081):
   for attempt in range(40):
    try:body,headers=request(port);break
    except (OSError,urllib.error.URLError):time.sleep(.1)
   else:raise AssertionError('Apache indisponible')
   body={k.lower():v for k,v in body.items()}
   assert body['host']=='localhost:19443',body
   assert body['x-forwarded-host']=='monapp-int.apps.example.com'
   assert body['x-forwarded-proto']=='https' and body['x-forwarded-port']=='443'
   assert 'forwarded' not in body
   assert 'MONAPP_INT_BACK=endpoint-1' in body['cookie']
   assert 'JSESSIONID=test' in body['cookie']
   cookies=headers.get_all('Set-Cookie')
   assert any('MONAPP_INT_BACK=endpoint-1' in c for c in cookies)
   assert any('Domain=monapp-int.apps.example.com' in c for c in cookies),cookies
   assert headers['Location']=='https://monapp-int.apps.example.com/login',headers
  assert 'localhost' in sni
  print('PASS: deux HTTPD, Host/SNI backend, X-Forwarded-Host public, cookies aller/retour et redirections HTTPS',flush=True)
  try:request(18082);raise AssertionError('Certificat au mauvais nom accepté')
  except urllib.error.HTTPError as e:assert e.code in (500,502),e.code
  print('PASS: certificat dont le nom ne correspond pas refusé (erreur proxy)',flush=True)
 except Exception:
  for log in logs:log.flush();log.seek(0);print(log.read()[-4000:])
  raise
 finally:
  for proc in processes:
   if proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=5)
    except subprocess.TimeoutExpired:proc.kill();proc.wait()
  if server:server.shutdown();server.server_close()
  for log in logs:log.close()
