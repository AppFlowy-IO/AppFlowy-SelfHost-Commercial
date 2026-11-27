"""Exercise login correlation with the Compose Nginx and pinned Auth, on a disposable stack."""
import argparse
import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import uuid

from images import ROOT, clean_environment


def exchange(port, method, path, headers=(), body=b''):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        connection.putrequest(method, path)
        for name, value in headers:
            connection.putheader(name, value)
        connection.putheader('Content-Length', str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        response.read()
        return response.status, response.headers
    finally:
        connection.close()


def check(nginx_config):
    with tempfile.TemporaryDirectory(prefix='appflowy-login-ingress-') as tmp:
        directory = Path(tmp)
        shutil.copy(ROOT / 'deploy.env', directory / '.env')
        shutil.copytree(ROOT / 'docker/nginx', directory / 'docker/nginx')
        (directory / 'docker/backup').mkdir()
        for env in (ROOT / 'docker/backup').glob('source-*.env'):
            shutil.copyfile(env, directory / 'docker/backup' / env.name)
        shutil.copyfile(nginx_config, directory / 'docker/nginx/nginx.conf')
        shutil.copyfile(ROOT / 'docker-compose.yml', directory / 'docker-compose.yml')
        # The Cloud probe echoes exactly the ID received at the second hop. Auth and
        # PostgreSQL use the shipped Compose definitions and pinned images.
        (directory / 'cloud.conf').write_text('''events {}
http { access_log off; server { listen 8000; add_header X-Request-ID $http_x_request_id always;
    add_header X-Fixture-Hit yes always; return 401; } }
''')
        (directory / 'probe.yml').write_text('''services:
  nginx:
    ports: !override ["127.0.0.1::80"]
    networks: !override [default]
  appflowy_cloud: !override
    image: nginx
    networks:
      default:
        aliases: [appflowy_cloud_default]
    volumes: ["./cloud.conf:/etc/nginx/nginx.conf:ro"]
networks:
  mcp_proxy:
    ipam:
      config: !override []
''')
        project = 'login-test-' + uuid.uuid4().hex[:12]

        def compose(*args):
            command = ['docker', 'compose', '-p', project, '--env-file', '.env',
                       '-f', 'docker-compose.yml', '-f', 'probe.yml', *args]
            result = subprocess.run(command, cwd=directory, env=clean_environment(),
                                    capture_output=True, text=True, timeout=300)
            if result.returncode:
                raise RuntimeError(f'Disposable Compose command failed ({args[0]})')
            return result.stdout

        compose('config', '--quiet')
        try:
            compose('up', '-d', '--wait', '--wait-timeout', '150', '--no-deps',
                    'postgres', 'gotrue', 'appflowy_cloud', 'nginx')
            compose('exec', '-T', 'nginx', 'nginx', '-t')
            port = int(compose('port', 'nginx', '80').strip().rsplit(':', 1)[1])
            login_id = 'Login.Edge_42'
            provided = [('X-Request-ID', login_id)]
            private = ['private-verify-bearer', 'private-login-password', 'private-proxy-query']
            path = '/gotrue/token?grant_type=password'
            status, headers = exchange(port, 'OPTIONS', path, [
                ('Origin', 'http://localhost'), ('Access-Control-Request-Method', 'POST'),
                ('Access-Control-Request-Headers', 'content-type,x-request-id')])
            assert status == 204 and 'x-request-id' in headers.get('Access-Control-Allow-Headers', '').lower()
            status, headers = exchange(port, 'POST', path, provided + [
                ('Origin', 'http://localhost'), ('Content-Type', 'application/json')],
                json.dumps({'email': 'unknown-user@example.org', 'password': private[1]}).encode())
            assert status == 400 and headers.get_all('X-Request-ID') == [login_id]
            assert 'x-request-id' in ','.join(headers.get_all('Access-Control-Expose-Headers', [])).lower()

            verify = '/api/user/verify/' + private[0] + '?token=' + private[2]
            for method, target in [('GET', verify), ('POST', '/api/auth/ldap/login')]:
                status, headers = exchange(port, method, target, provided)
                assert status == 401 and headers.get('X-Fixture-Hit') == 'yes'
                assert headers.get_all('X-Request-ID') == [login_id]
            generated = set()
            for ids in [[], ['.'], ['..'], ['invalid id'], ['z' * 129], ['one', 'two']]:
                status, headers = exchange(port, 'GET', verify, [('X-Request-ID', i) for i in ids])
                actual = headers.get_all('X-Request-ID', [])
                assert status == 401 and len(actual) == 1 and re.fullmatch('[a-f0-9]{32}', actual[0])
                assert actual[0] not in generated
                generated.add(actual[0])
            status, headers = exchange(port, 'GET', '/api/ordinary', provided + [('Referer', verify)])
            assert status == 401 and re.fullmatch('[a-f0-9]{32}', headers['X-Request-ID'])
            # Keep the container's DNS/IP stable but close the Cloud port. This
            # reproduces a real upstream refusal without waiting on an ARP timeout.
            cloud = directory / 'cloud.conf'
            cloud.write_text(cloud.read_text().replace('listen 8000', 'listen 8001'))
            compose('exec', '-T', 'appflowy_cloud', 'nginx', '-s', 'reload')
            until = time.monotonic() + 4
            while True:
                status, headers = exchange(port, 'GET', verify, provided)
                if status == 502 or time.monotonic() >= until:
                    break
                time.sleep(.1)
            assert status == 502 and headers.get_all('X-Request-ID') == [login_id]
            until = time.monotonic() + 3
            while True:
                logs = compose('logs', '--no-log-prefix', 'nginx')
                assert all(value not in logs for value in private), 'private input reached Nginx output'
                events = [json.loads(line) for line in logs.splitlines() if line.startswith('{"request_id"')]
                found = {(e['operation'], e['status']) for e in events if e['request_id'] == login_id}
                if {('token_exchange', 400), ('ldap_login', 401), ('verify_login', 401), ('verify_login', 502)} <= found:
                    break
                if time.monotonic() >= until:
                    raise AssertionError('Missing request-correlated proxy status')
                time.sleep(.1)
            assert all(set(e) == {'request_id', 'operation', 'status', 'time'} for e in events)
        finally:
            compose('down', '--volumes', '--remove-orphans')
    print('Password, LDAP, verification, proxy outage, ID validation, CORS and log privacy passed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nginx-config', type=Path, default=ROOT / 'docker/nginx/nginx.conf')
    check(parser.parse_args().nginx_config)
