#!/usr/bin/env python3
"""Prepare a reviewed deployment-image update from a publisher notification."""
import argparse
import json
import os
from pathlib import Path
import re

import yaml

from images import ROOT, command

SOURCES = {
    'cloud': 'AppFlowy-IO/AppFlowy-Docker-CI',
    'web': 'AppFlowy-IO/AppFlowy-Web',
}
SERVICES = {
    'gotrue': ('gotrue', 'gotrue'),
    'appflowy_cloud': ('appflowy_cloud', 'appflowy-cloud'),
    'appflowy_worker': ('appflowy_worker', 'appflowy-worker'),
    'appflowy_search': ('appflowy_search', 'appflowy-search'),
    'appflowy_backup': ('appflowy_backup', 'appflowy-backup'),
    'ai': ('appflowy_ai', 'appflowy-ai'),
    'appflowy_web': ('appflowy_web', 'appflowy-web'),
}
DEFAULT_SERVICES = {
    'cloud': ['appflowy_cloud', 'appflowy_worker', 'appflowy_search'],
    'web': ['appflowy_web'],
}
DIGEST = re.compile(r'sha256:[0-9a-f]{64}')
VERSION = re.compile(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
                     r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?')


def version_key(tag):
    match = VERSION.fullmatch(tag)
    if not match or len(tag) > 120:
        raise ValueError('Expected a version tag such as 0.20.0 or v0.20.0; moving aliases are not releases')
    prerelease = match[4]
    parts = tuple((0, int(part)) if part.isdigit() else (1, part)
                  for part in prerelease.split('.')) if prerelease else ()
    return (*map(int, match.group(1, 2, 3)), prerelease is None, parts)


def notification(event_name, event):
    if event_name == 'repository_dispatch' and event.get('action') == 'selfhost-images-published':
        payload = event['client_payload']
        source = payload['source']
        if payload.get('source_repository') != SOURCES.get(source):
            raise ValueError('Unexpected publisher repository')
        services = payload['services']
        tag = payload['tag']
        url = payload.get('source_url', '')
    elif event_name == 'workflow_dispatch':
        payload = event['inputs']
        source, tag = payload['source'], payload['tag']
        services = ([part.strip() for part in payload['services'].split(',')]
                    if payload.get('services') else DEFAULT_SERVICES.get(source, []))
        url = ''
    else:
        raise ValueError('Unsupported release event')
    if source not in SOURCES or not isinstance(tag, str):
        raise ValueError('Unknown release source or invalid tag')
    if url and not re.fullmatch(r'https://github\.com/' + re.escape(SOURCES[source])
                               + r'/(?:actions/runs/[0-9]+|releases/tag/[0-9A-Za-z_.%-]+)', url):
        raise ValueError('Unexpected release provenance URL')
    return source, tag, services, url


def release_digest(reference):
    """Pin the index, preserving both supported CPU architectures."""
    manifest = json.loads(command('docker', 'buildx', 'imagetools', 'inspect', reference,
                                  '--format', '{{json .Manifest}}'))
    digest = manifest.get('digest', '')
    platforms = {(row.get('platform', {}).get('os'), row.get('platform', {}).get('architecture'))
                 for row in manifest.get('manifests', [])}
    if not DIGEST.fullmatch(digest):
        raise ValueError(reference + ': missing or invalid image-index digest')
    if not {('linux', 'amd64'), ('linux', 'arm64')} <= platforms:
        raise ValueError(reference + ': release images must support linux/amd64 and linux/arm64')
    return digest


def block(text, key):
    indentation = re.match(r' *', key)[0]
    match = re.search(r'^' + re.escape(key) + r':\n.*?(?=^' + indentation
                      + r'[^\s#][^\n]*:\n|\Z)', text, re.M | re.S)
    if not match:
        raise ValueError('Missing YAML block: ' + key)
    return match


def image_tag(reference):
    reference = re.sub(r'\$\{[A-Z_]+:-([^}]+)\}', r'\1', reference)
    return reference.split('@')[0].rsplit(':', 1)[-1]


def update_branch(source, tag, services):
    branch = f'automation/image-updates/{source}-{tag}'
    if source == 'cloud':
        # A later GoTrue-only build of the same version must not replace an open Cloud/Worker PR.
        branch += '-' + '-'.join(service.removeprefix('appflowy_') for service in sorted(services))
    return branch


def prepare_update(root, source, tag, services, resolve=release_digest):
    if source not in SOURCES or not isinstance(tag, str):
        raise ValueError('Unknown release source or invalid tag')
    # Defense in depth: test events never inspect a registry or modify a file.
    if tag.endswith('_test'):
        return [], 'Test image tags are ignored'
    proposed = version_key(tag)
    allowed = set(SERVICES) - {'appflowy_web'} if source == 'cloud' else {'appflowy_web'}
    if (not isinstance(services, list) or not services or any(not isinstance(item, str) for item in services)
            or len(services) != len(set(services)) or not set(services) <= allowed):
        raise ValueError('The release must identify unique services published by its source')
    if ('appflowy_cloud' in services) != ('appflowy_worker' in services):
        raise ValueError('Cloud and Worker must be updated together')

    compose_path = root / 'docker-compose.yml'
    helm_path = root / 'helm/appflowy-cloud/values.yaml'
    compose, helm = compose_path.read_text(), helm_path.read_text()
    config, chart = yaml.safe_load(compose), yaml.safe_load(helm)
    for service in services:
        previous = config['services'][service]['image']
        old_tag = image_tag(previous)
        if VERSION.fullmatch(old_tag) and version_key(old_tag) > proposed:
            return [], f'Ignored stale {tag} notification: {service} already uses {old_tag}'

    changes = []
    for service in sorted(services):
        repository, helm_key = SERVICES[service]
        repository = 'appflowyinc/' + repository
        previous = config['services'][service]['image']
        if previous.split(':', 1)[0].split('@')[0] != repository:
            raise ValueError(service + ': unexpected Compose image repository')
        if chart[helm_key]['image']['repository'] != repository:
            raise ValueError(service + ': unexpected Helm image repository')
        digest = resolve(repository + ':' + tag)
        if not DIGEST.fullmatch(digest):
            raise ValueError(service + ': invalid image digest')
        old_digest = previous.partition('@')[2]
        if (old_digest and VERSION.fullmatch(image_tag(previous))
                and version_key(image_tag(previous)) == proposed and old_digest != digest):
            raise ValueError(service + ': an existing release tag was republished; publish a new version')
        reference = repository + ':' + tag + '@' + digest
        service_block = block(compose, '  ' + service)
        updated, count = re.subn(r'^(    image:) [^\n]+$', lambda m: m[1] + ' ' + reference,
                                 service_block[0], count=1, flags=re.M)
        if count != 1:
            raise ValueError(service + ': expected exactly one Compose image line')
        compose = compose[:service_block.start()] + updated + compose[service_block.end():]

        chart_block = block(helm, helm_key)
        updated, count = re.subn(r'^    tag: [^\n]+$', lambda _: f'    tag: "{tag}"',
                                 chart_block[0], count=1, flags=re.M)
        if count != 1:
            raise ValueError(service + ': expected exactly one Helm image tag')
        if re.search(r'^    digest:', updated, re.M):
            updated = re.sub(r'^    digest: [^\n]+$', lambda _: '    digest: ' + digest, updated, flags=re.M)
        else:
            updated = re.sub(r'^(    tag: [^\n]+\n)', lambda m: m[1] + '    digest: ' + digest + '\n',
                             updated, count=1, flags=re.M)
        helm = helm[:chart_block.start()] + updated + helm[chart_block.end():]
        if previous != reference:
            changes.append((service, previous, reference))

    # Do not leave a partially updated deployment when any selected image fails validation.
    if changes:
        compose_path.write_text(compose)
        helm_path.write_text(helm)
    return changes, 'Prepared exact image pins' if changes else 'Images are already pinned'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--event', type=Path, default=os.environ.get('GITHUB_EVENT_PATH'), required=False)
    parser.add_argument('--body', type=Path, required=True)
    args = parser.parse_args()
    if not args.event:
        parser.error('--event or GITHUB_EVENT_PATH is required')
    source, tag, services, url = notification(os.environ['GITHUB_EVENT_NAME'], json.loads(args.event.read_text()))
    changes, reason = prepare_update(ROOT, source, tag, services)
    print(reason)
    if changes:
        body = [f'Update the published {source} images to `{tag}` with immutable multi-platform digests.', '',
                f'Publisher: [{SOURCES[source]}]({url or "https://github.com/" + SOURCES[source]})', '',
                '| Service | Previous image | Proposed image |', '| --- | --- | --- |']
        body += [f'| {service} | `{before}` | `{after}` |' for service, before, after in changes]
        body += ['', 'Compose, generated Swarm files, and Helm use the same image pins.',
                 'The deployment checks use the proposed pins without CI baseline image overrides.',
                 'Review compatibility and migration requirements before merging. This PR does not deploy services.', '']
        args.body.write_text('\n'.join(body))
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        with open(output, 'a') as stream:
            stream.write('changed=' + str(bool(changes)).lower() + '\n')
            if changes:
                stream.write(f'source={source}\ntag={tag}\nbranch={update_branch(source, tag, services)}\n')


if __name__ == '__main__':
    main()
