#!/usr/bin/env python3
"""Manage only this folder's isolated, single-node local Swarm experiment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

import yaml

HERE = Path(__file__).resolve().parent
OUT = Path(os.environ.get('SWARM_TEST_DIR', str(HERE / '.local'))).expanduser().resolve()


def run(*args, capture=False):
    return subprocess.run(list(args), check=True, text=True, capture_output=capture)


def docker(*args):
    return run('docker', *args, capture=True).stdout.strip()


def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    OUT.chmod(0o700)
    path = OUT / name
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(json.dumps(value, indent=2) + '\n')
    path.chmod(0o600)


def read(name):
    return json.loads((OUT / name).read_text())


def local_engine():
    context = json.loads(docker('context', 'inspect', docker('context', 'show')))[0]
    context_endpoint = context['Endpoints']['docker']['Host']
    # Docker's explicit context takes precedence over DOCKER_HOST.
    endpoint = context_endpoint if os.environ.get('DOCKER_CONTEXT') else os.environ.get('DOCKER_HOST') or context_endpoint
    if not endpoint.startswith(('unix://', 'npipe://')):
        raise SystemExit('This harness requires a local Docker socket; remote Docker endpoints are unsupported.')
    return json.loads(docker('info', '--format', '{{json .Swarm}}'))


def stack_name():
    metadata = read('metadata.json')
    name = metadata['stack_name']
    if not metadata.get('local_experiment_only') or not name.startswith('af-swarm-'):
        raise SystemExit('Refusing a stack without this harness local-test metadata and af-swarm- name prefix.')
    return name


def service_ids(stack):
    return set(docker('service', 'ls', '-q', '--filter', f'label=com.docker.stack.namespace={stack}').split())


def owned(stack):
    ids = service_ids(stack)
    owner = read('ownership.json') if (OUT / 'ownership.json').exists() else {}
    if ids and (owner.get('stack_name') != stack or set(owner.get('service_ids', [])) != ids):
        raise SystemExit('Existing service IDs do not match this local test. Refusing to modify another stack.')
    return ids


def containers(service):
    ids = docker('ps', '-q', '--filter', f'label=com.docker.swarm.service.name={service}').split()
    return json.loads(docker('inspect', *ids)) if ids else []


def wait_ready(stack, services, replaced=None, timeout=240):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        states = []
        ready = True
        for name in services:
            rows = containers(f'{stack}_{name}')
            health = [row['State'].get('Health', {}).get('Status', row['State']['Status']) for row in rows]
            states.append(name + '=' + ('/'.join(health) or 'pending'))
            ready = ready and len(rows) == 1 and health[0] in ('healthy', 'running')
            if replaced:
                ready = ready and all(row['Id'] not in replaced for row in rows)
        message = ' '.join(states)
        if message != last:
            print(message, flush=True)
            last = message
        if ready:
            return
        time.sleep(3)
    raise SystemExit('Readiness deadline exceeded; inspect local.py status and docker service logs for this stack.')


def up(no_pull):
    state = local_engine()
    env = dict(os.environ)
    env['SWARM_PULL_IMAGES'] = '0' if no_pull else '1'
    subprocess.run([sys.executable, str(HERE / 'prepare.py')], env=env, check=True)
    stack = stack_name()
    if state['LocalNodeState'] == 'inactive':
        # Capture stdout because swarm init prints join credentials.
        docker('swarm', 'init', '--default-addr-pool', '10.240.0.0/16', '--default-addr-pool-mask-length', '24')
        state = local_engine()
        write('created-swarm.json', {'node_id': state['NodeID'], 'original_state': 'inactive'})
    if not state.get('ControlAvailable') or len(docker('node', 'ls', '-q').split()) != 1:
        raise SystemExit('This local harness requires a single-node Swarm manager.')
    owned(stack)
    docker('node', 'update', '--label-add', 'appflowy-swarm-test=true', state['NodeID'])
    # Staging intentionally stops application writers before reapplying the bootstrap config.
    # It must never be used as an automatic production rolling-upgrade procedure.
    if service_ids(stack):
        specs = json.loads(docker('service', 'inspect', *sorted(service_ids(stack))))
        names = [s['Spec']['Name'] for s in specs if s['Spec']['Name'].rsplit('_', 1)[-1] not in ('postgres', 'redis', 'minio')]
        if names:
            docker('service', 'scale', '--detach', *[f'{name}=0' for name in names])
            deadline = time.monotonic() + 120
            while any(containers(name) for name in names):
                if time.monotonic() > deadline:
                    raise SystemExit('Timed out stopping local test writers before startup.')
                time.sleep(2)
    write('ownership.json', {'stack_name': stack, 'service_ids': sorted(service_ids(stack)),
                             'deployment_pending': True})
    try:
        run('docker', 'stack', 'deploy', '--resolve-image', 'never', '-c', str(OUT / 'docker-stack.yml'), stack)
    finally:
        # A rejected later service may leave an earlier part of the stack running.
        # Retain ownership of those tasks so rerun/down can recover the partial deployment.
        write('ownership.json', {'stack_name': stack, 'service_ids': sorted(service_ids(stack))})
    stages = read('metadata.json')['stages']
    wait_ready(stack, stages[0])
    for stage in stages[1:]:
        docker('service', 'scale', '--detach', *[f'{stack}_{name}=1' for name in stage])
        wait_ready(stack, stage)
    running = yaml.safe_load((OUT / 'docker-stack.yml').read_text())
    for service in running['services'].values():
        service['deploy']['replicas'] = 1
    path = OUT / 'docker-stack.running.yml'
    path.write_text(yaml.safe_dump(running, sort_keys=False))
    path.chmod(0o600)
    http_checks()
    print('Local Swarm ready: ' + read('metadata.json')['base_url'])


def http_checks():
    base = read('metadata.json')['base_url']
    results = []
    for path in ('/api/health', '/gotrue/health', '/', '/console'):
        with urllib.request.urlopen(base + path, timeout=20) as response:
            if response.status != 200:
                raise SystemExit(f'HTTP readiness failed: {path} returned {response.status}')
            results.append({'path': path, 'status': response.status})
    write('http-results.json', results)


def replace(names):
    local_engine()
    stack = stack_name()
    owned(stack)
    allowed = set(read('metadata.json')['images'])
    if not names or any(name not in allowed for name in names):
        raise SystemExit('Choose test services from: ' + ', '.join(sorted(allowed)))
    path = OUT / 'replacement-results.json'
    results = read(path.name) if path.exists() else []
    for name in names:
        service = f'{stack}_{name}'
        before = {row['Id'] for row in containers(service)}
        spec = json.loads(docker('service', 'inspect', service))[0]
        if spec['Spec']['Mode']['Replicated']['Replicas'] != 1:
            raise SystemExit(f'{name} must already have exactly one running replica.')
        started = time.monotonic()
        docker('service', 'update', '--force', '--detach', service)
        wait_ready(stack, [name], replaced=before)
        results.append({'service': name, 'before_ids': sorted(before), 'after_id': containers(service)[0]['Id'],
                        'seconds': round(time.monotonic() - started, 2)})
        write(path.name, results)
    if 'appflowy_cloud' in names and (OUT / 'ui-replacement-ready.json').exists():
        (OUT / 'ui-replacement-complete').touch(mode=0o600)


def down(leave_swarm):
    state = local_engine()
    if state['LocalNodeState'] == 'inactive':
        print('Swarm is already inactive; local volumes retained.')
        return
    stack = stack_name()
    if owned(stack):
        run('docker', 'stack', 'rm', stack)
    deadline = time.monotonic() + 120
    while docker('ps', '-q', '--filter', f'label=com.docker.stack.namespace={stack}'):
        if time.monotonic() > deadline:
            raise SystemExit('Local tasks are still stopping; refusing to leave Swarm.')
        time.sleep(2)
    if leave_swarm:
        created = read('created-swarm.json') if (OUT / 'created-swarm.json').exists() else {}
        if (created.get('node_id') != state['NodeID'] or docker('service', 'ls', '-q')
                or len(docker('node', 'ls', '-q').split()) != 1):
            raise SystemExit('Refusing to leave Swarm: it was not created here, or other services remain.')
        run('docker', 'swarm', 'leave', '--force')
    print('Local test stack stopped. Data volumes and evidence retained.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    subs.add_parser('check')
    start = subs.add_parser('up')
    start.add_argument('--no-pull', action='store_true', help='Use locally cached image digests.')
    subs.add_parser('status')
    subs.add_parser('test')
    subs.add_parser('verify')
    restart = subs.add_parser('replace')
    restart.add_argument('services', nargs='+')
    stop = subs.add_parser('down')
    stop.add_argument('--leave-swarm', action='store_true')
    args = parser.parse_args()
    if args.command == 'check':
        run(sys.executable, str(HERE / 'generate.py'), '--check')
    elif args.command == 'up':
        up(args.no_pull)
    elif args.command == 'status':
        local_engine()
        run('docker', 'stack', 'services', stack_name())
        run('docker', 'stack', 'ps', '--no-trunc', stack_name())
    elif args.command in ('test', 'verify'):
        local_engine()
        owned(stack_name())
        http_checks()
        phase = 'create' if args.command == 'test' else 'verify'
        run(sys.executable, str(HERE / 'tests/api_smoke.py'), phase)
        run(sys.executable, str(HERE / 'tests/database_row_smoke.py'), phase)
    elif args.command == 'replace':
        replace(args.services)
    elif args.command == 'down':
        down(args.leave_swarm)


if __name__ == '__main__':
    main()
