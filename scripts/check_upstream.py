#!/usr/bin/env python3
"""Resolve the latest stable upstream release without publishing or committing."""
import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def version_tuple(value):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('expected a stable X.Y.Z version: ' + value)
    return tuple(map(int, value.split('.')))


def resolve_lock(lock, release, commit):
    if release['draft'] or release['prerelease']:
        return dict(lock)
    tag = release['tag_name']
    latest = version_tuple(tag.removeprefix('v'))
    current = version_tuple(lock['version'].removeprefix('v'))
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('invalid upstream commit SHA')
    if latest < current:
        return dict(lock)
    if latest == current:
        if tag != lock['version'] or commit != lock['commit']:
            raise ValueError('upstream release tag changed; manual review required')
        return dict(lock)
    major, minor, patch = version_tuple(lock['package_version'])
    return lock | {'version': tag, 'commit': commit,
                   'package_version': f'{major}.{minor}.{patch + 1}'}


def release_complete(release, version):
    if not release or release['draft'] or release['prerelease']:
        return False
    uploaded = {asset['name'] for asset in release['assets']
                if asset['state'] == 'uploaded' and asset['size'] > 0}
    expected = {f'magpie-{version}-{arch}{suffix}'
                for arch in ('x86', 'arm64')
                for suffix in ('.fpk', '.fpk.sha256', '.build-info.json')}
    return expected <= uploaded


def github_api(path, *, missing_ok=False):
    headers = {'Accept': 'application/vnd.github+json',
               'User-Agent': 'magpie-fpk-upstream-check',
               'X-GitHub-Api-Version': '2022-11-28'}
    if os.environ.get('GH_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GH_TOKEN']
    request = urllib.request.Request('https://api.github.com/repos/' + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404 and missing_ok:
            return None
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', type=Path, default=Path('upstream.lock.json'))
    args = parser.parse_args()
    lock = json.loads(args.lock.read_text(encoding='utf-8'))
    if lock['repository'] != 'yetone/magpie':
        raise ValueError('unexpected upstream repository')
    upstream = lock['repository']
    release = github_api(upstream + '/releases/latest')
    # Resolve the tag itself, never target_commitish (which may be a moving branch).
    tag = urllib.parse.quote(release['tag_name'], safe='')
    commit = github_api(upstream + '/commits/' + tag)['sha']
    updated = resolve_lock(lock, release, commit)
    version = updated['package_version']
    existing = github_api(os.environ['GITHUB_REPOSITORY'] + '/releases/tags/fpk-v' + version,
                          missing_ok=True)
    should_build = updated != lock or not release_complete(existing, version)
    source_ref = os.environ['GITHUB_SHA']
    if should_build and updated == lock:
        # A previous run may have pushed the tag before publication failed.
        # Rebuild its exact packaging source even if main has since advanced.
        tagged = github_api(os.environ['GITHUB_REPOSITORY'] + '/commits/fpk-v' + version,
                            missing_ok=True)
        if tagged:
            source_ref = tagged['sha']
    if not re.fullmatch('[0-9a-f]{40}', source_ref):
        raise ValueError('invalid package source commit SHA')
    args.lock.write_text(json.dumps(updated, indent=2) + '\n', encoding='utf-8')
    with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as out:
        out.write(f'should_build={str(should_build).lower()}\n')
        out.write(f'source_ref={source_ref}\n')
    print(f'Upstream {updated["version"]} -> package {version}; build={should_build}')


if __name__ == '__main__':
    main()
