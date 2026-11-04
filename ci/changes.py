#!/usr/bin/env python3
"""Select CI coverage from the actual diff, including PR and post-merge pushes."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

import yaml

WEB_FILES = {'docker-compose.yml', 'docker-swarm/docker-stack.yml',
             'helm/appflowy-cloud/values.yaml'}
WEB_PIN = re.compile(r'appflowyinc/appflowy_web:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}'
                     r'@sha256:[0-9a-f]{64}')
SHA = re.compile(r'[0-9a-f]{40}')


def git(*args):
    return subprocess.run(['git', *args], check=True, capture_output=True).stdout.decode()


def remove_web_pin(document, path):
    if path == 'helm/appflowy-cloud/values.yaml':
        image = document['appflowy-web']['image']
        tag, digest = image.pop('tag'), image.pop('digest', '')
        return f"{image['repository']}:{tag}@{digest}"
    return document['services']['appflowy_web'].pop('image')


def web_images_only(paths, before, after):
    if not paths or not set(paths) <= WEB_FILES:
        return False
    pins, changed = set(), False
    try:
        # Read all three targets, even if one was omitted from the diff. A partial
        # update must not skip the runtime checks that enforce image parity.
        for path in sorted(WEB_FILES):
            old, new = yaml.safe_load(before(path)), yaml.safe_load(after(path))
            old_pin, new_pin = remove_web_pin(old, path), remove_web_pin(new, path)
            if old != new or not WEB_PIN.fullmatch(new_pin):
                return False
            pins.add(new_pin)
            changed |= old_pin != new_pin
    except (KeyError, TypeError, AttributeError, yaml.YAMLError, subprocess.CalledProcessError):
        return False
    return changed and len(pins) == 1


def classify(paths, before, after):
    relevant = [path for path in paths if path != 'README.md' and not path.startswith('docs/')]
    if paths and not relevant:
        return 'docs'
    if web_images_only(relevant, before, after):
        return 'web-images'
    return 'integration'


def event_range(name, event):
    if name == 'pull_request':
        pr = event['pull_request']
        # Match GitHub's PR diff, excluding unrelated changes on the base branch.
        return git('merge-base', pr['base']['sha'], pr['head']['sha']).strip(), pr['head']['sha']
    if name == 'push' and event['before'] != '0' * 40:
        return event['before'], event['after']
    # Manual qualification and a new branch always get the full suite.
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base')
    parser.add_argument('--head')
    args = parser.parse_args()
    if bool(args.base) != bool(args.head):
        parser.error('--base and --head must be supplied together')
    revisions = (args.base, args.head) if args.base else event_range(
        os.environ.get('GITHUB_EVENT_NAME'),
        json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text()))
    kind = 'integration'
    if revisions:
        base, head = revisions
        if not all(SHA.fullmatch(revision) for revision in revisions):
            parser.error('Expected full Git commit SHAs')
        paths = git('diff', '--name-only', '--no-renames', '-z', base, head).rstrip('\0').split('\0')
        paths = [path for path in paths if path]
        kind = classify(paths, lambda path: git('show', f'{base}:{path}'),
                        lambda path: git('show', f'{head}:{path}'))
    outputs = {'kind': kind, 'run_checks': str(kind != 'docs').lower(),
               'run_integration': str(kind == 'integration').lower()}
    print(json.dumps(outputs))
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a') as stream:
            stream.writelines(f'{key}={value}\n' for key, value in outputs.items())


if __name__ == '__main__':
    main()
