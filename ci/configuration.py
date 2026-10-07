"""Render only versioned deployment inputs, never an operator's restore selections."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    'deploy.env', 'docker-compose.yml', 'docker-compose.backup.yml',
    'docker/nginx/nginx.conf', 'docker/nginx/ssl/certificate.crt',
    'docker/nginx/ssl/private_key.key', 'docker-swarm/docker-stack.yml',
    'docker-swarm/docker-stack.backup.yml',
    'docker/backup/source-ai.env', 'docker/backup/source-appflowy_cloud.env',
    'docker/backup/source-appflowy_worker.env', 'docker/backup/source-appflowy_search.env',
    'docker/backup/source-appflowy_backup.env', 'helm/appflowy-cloud/values.yaml',
    'helm/appflowy-cloud/Chart.yaml', 'helm/appflowy-cloud/Chart.lock', 'ci/helm-values.yaml',
) + tuple(sorted(str(path.relative_to(ROOT)) for path in
                 (ROOT / 'helm/appflowy-cloud/templates').rglob('*') if path.is_file()))


def source_fingerprint(root=ROOT, files=SOURCE_FILES):
    digest = hashlib.sha256()
    if (not isinstance(files, (list, tuple)) or not files
            or not all(isinstance(name, str) for name in files) or len(files) != len(set(files))):
        raise RuntimeError('Deployment source manifest must contain unique relative file names')
    for name in files:
        if (not isinstance(name, str) or not name or Path(name).is_absolute()
                or '..' in Path(name).parts or '\\' in name):
            raise RuntimeError('Deployment source manifest must contain relative file names without traversal')
        source = root / name
        if source.is_symlink() or not source.is_file() or root.resolve() not in source.resolve().parents:
            raise RuntimeError('Deployment source must be a regular file within its source directory')
        digest.update(name.encode() + b'\0')
        digest.update(hashlib.sha256(source.read_bytes()).digest())
    return digest.hexdigest()


def isolated_source(destination, root=ROOT):
    """Copy the explicit public source manifest, excluding .env and backup-ops entirely."""
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in SOURCE_FILES:
        source, target = root / name, destination / name
        if source.is_symlink() or not source.is_file():
            raise RuntimeError('Deployment source must be a regular checked-in file: ' + name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return destination


def check_compose(environment=None):
    result = subprocess.run(['docker', 'compose', 'version', '--short'], env=environment,
                            text=True, capture_output=True, timeout=30)
    match = re.search(r'v?(\d+)\.(\d+)\.(\d+)', result.stdout)
    if result.returncode or not match or tuple(map(int, match.groups())) < (2, 30, 0):
        raise RuntimeError('Docker Compose 2.30 or newer is required for Backup restore-selection files')
    return match.group(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-tools', action='store_true', required=True)
    parser.parse_args()
    print('Docker Compose ' + check_compose() + ': supported')
