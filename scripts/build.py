#!/usr/bin/env python3
"""Build the pinned Magpie source and package it with the official fnpack."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import tarfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
DIST = ROOT / 'dist'


def validate_version(value):
    if not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', value):
        raise ValueError('package version must be X.Y.Z, without a v prefix')
    return value


def platform_for(arch):
    if arch not in ('amd64', 'arm64'):
        raise ValueError('unsupported architecture: ' + arch)
    return {'amd64': 'x86', 'arm64': 'arm'}[arch]


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(url, path, expected=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and expected and sha256(path) == expected:
        return
    temporary = path.with_suffix(path.suffix + '.part')
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'magpie-fpk-builder'})
            with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as out:
                shutil.copyfileobj(response, out)
            if expected and sha256(temporary) != expected:
                raise ValueError('SHA256 mismatch: ' + url)
            temporary.replace(path)
            return
        except (OSError, ValueError):
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2)


def extract_source(archive, destination):
    with tarfile.open(archive, 'r:gz') as source:
        members = source.getmembers()
        roots = {member.name.split('/')[0] for member in members}
        if len(roots) != 1:
            raise ValueError('upstream archive must contain one root directory')
        for member in members:
            parts = Path(member.name).parts
            if member.name.startswith('/') or '..' in parts or not (member.isfile() or member.isdir()):
                raise ValueError('unsafe upstream archive entry: ' + member.name)
        destination.mkdir(parents=True, exist_ok=False)
        for member in members:
            relative = Path(*Path(member.name).parts[1:])
            if not relative.parts:
                continue
            target = destination / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as stream, target.open('wb') as out:
                    shutil.copyfileobj(stream, out)
                target.chmod(member.mode & 0o777)


def fetch_source(lock):
    commit = lock['commit']
    if not re.fullmatch('[0-9a-f]{40}', commit) or lock['repository'] != 'yetone/magpie':
        raise ValueError('invalid upstream lock')
    destination = BUILD / 'upstream'
    marker = destination / '.fpk-source-commit'
    if marker.exists() and marker.read_text().strip() == commit:
        return destination
    if destination.exists():
        raise ValueError('build/upstream belongs to another source; use a clean build directory')
    archive = BUILD / (commit + '.tar.gz')
    download(f'https://codeload.github.com/{lock["repository"]}/tar.gz/{commit}', archive)
    extract_source(archive, destination)
    marker.write_text(commit + '\n', encoding='utf-8')
    return destination


def protect_updates(source):
    """Fail closed when upstream signatures change; keep the patch explicit."""
    patches = {
        'gui': {
            'func (u *updater) start() {': '\n\tif fnosManaged { u.stuck = "not-writable"; return }',
            'func (u *updater) begin() bool {': '\n\tif fnosManaged { return false }',
        },
        'update': {
            'func StageBinary(ctx context.Context, rel *Release) (string, error) {':
                '\n\tif fnosManaged { return "", fmt.Errorf("update Magpie using the fnOS FPK package") }',
            'func InstallBinaryAside(staged, exe string) (string, error) {':
                '\n\tif fnosManaged { return "", fmt.Errorf("update Magpie using the fnOS FPK package") }',
            'func InstallBinaryAsAdmin(staged, exe string) error {':
                '\n\tif fnosManaged { return fmt.Errorf("update Magpie using the fnOS FPK package") }',
        },
    }
    changes = []
    for package, replacements in patches.items():
        path = source / 'internal' / package / 'update.go'
        content = path.read_text(encoding='utf-8')
        for signature, guard in replacements.items():
            if content.count(signature) != 1:
                raise ValueError('upstream update signature changed: ' + signature)
            if signature + guard not in content:
                content = content.replace(signature, signature + guard)
        changes.append((package, path, content))
    for package, path, content in changes:
        path.write_text(content, encoding='utf-8', newline='\n')
        (path.parent / 'fnos_managed.go').write_text(
            f'package {package}\n\n// This binary is managed by the fnOS application center.\nvar fnosManaged = true\n',
            encoding='utf-8')


def png_size(path):
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n' or len(data) > 1024 * 1024:
        raise ValueError('invalid PNG icon: ' + str(path))
    return struct.unpack('>II', data[16:24])


def prepare_package(source, binary, destination, arch, version, lock):
    validate_version(version)
    target_platform = platform_for(arch)
    shutil.copytree(ROOT / 'packaging/magpie', destination)
    manifest = (destination / 'manifest').read_text(encoding='utf-8')
    manifest = manifest.replace('@VERSION@', version).replace('@PLATFORM@', target_platform)
    (destination / 'manifest').write_text(manifest, encoding='utf-8', newline='\n')
    (destination / 'app/bin').mkdir()
    shutil.copy2(binary, destination / 'app/bin/magpie')
    (destination / 'app/bin/magpie').chmod(0o755)
    for size, original, package_icon in [(64, 'icon.png', 'ICON.PNG'), (256, 'icon-256.png', 'ICON_256.PNG')]:
        icon = source / 'internal/gui' / original
        if png_size(icon) != (size, size):
            raise ValueError('wrong upstream icon dimensions')
        shutil.copy2(icon, destination / package_icon)
        images = destination / 'app/ui/images'
        images.mkdir(exist_ok=True)
        shutil.copy2(icon, images / f'icon_{size}.png')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES'):
        shutil.copy2(source / name, destination / 'app' / name)
    shutil.copy2(source / 'LICENSE', destination / 'LICENSE')
    provenance = {'package_version': version, 'architecture': arch, 'upstream': lock,
                  'binary_sha256': sha256(binary), 'patch': 'fnos-managed-update-guard-v1'}
    (destination / 'app/build-info.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    for path in (destination / 'cmd').iterdir():
        path.chmod(0o755)
    return provenance


def run(command, **kwargs):
    print('+', ' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=['amd64', 'arm64'])
    parser.add_argument('--version')
    parser.add_argument('--fetch-only', action='store_true')
    args = parser.parse_args()
    lock = json.loads((ROOT / 'upstream.lock.json').read_text(encoding='utf-8'))
    version = validate_version(args.version or lock['package_version'])
    source = fetch_source(lock)
    if args.fetch_only:
        print(source)
        return
    if not args.arch:
        parser.error('--arch is required for a build')
    arch = args.arch
    protect_updates(source)
    run(['gofmt', '-w', source / 'internal/gui/update.go', source / 'internal/update/update.go',
         source / 'internal/gui/fnos_managed.go', source / 'internal/update/fnos_managed.go'])
    env = os.environ | {'CGO_ENABLED': '0', 'GOOS': 'linux', 'GOARCH': arch}
    binary = BUILD / f'magpie-{arch}'
    run(['go', 'build', '-tags', 'nogui', '-trimpath', '-ldflags',
         f'-s -w -X main.version={lock["version"]}', '-o', binary, '.'], cwd=source, env=env)
    with binary.open('rb') as stream:
        header = stream.read(20)
    if header[:6] != b'\x7fELF\x02\x01' or struct.unpack('<H', header[18:20])[0] != {'amd64': 62, 'arm64': 183}[arch]:
        raise ValueError('compiled ELF architecture does not match requested target')
    destination = BUILD / f'package-{arch}-{version}'
    provenance = prepare_package(source, binary, destination, arch, version, lock)
    if platform.system() != 'Linux':
        raise ValueError('official packaging runs on Linux; use GitHub Actions')
    if platform.machine() not in ('x86_64', 'amd64'):
        raise ValueError('packaging requires a Linux x86_64 host; both targets are cross-compiled')
    host = 'amd64'
    tool = lock['fnpack']
    fnpack = BUILD / ('fnpack-' + host)
    download(tool['url'], fnpack, tool['sha256'])
    fnpack.chmod(0o755)
    run([fnpack, 'build', '--directory', destination], cwd=BUILD)
    packages = list(destination.glob('*.fpk')) + list(BUILD.glob('magpie*.fpk'))
    if len(packages) != 1:
        raise ValueError('expected exactly one fnpack output, got ' + str(packages))
    DIST.mkdir(exist_ok=True)
    output = DIST / f'magpie-{version}-{"x86" if arch == "amd64" else "arm64"}.fpk'
    shutil.move(packages[0], output)
    provenance['fpk_sha256'] = sha256(output)
    output.with_suffix('.build-info.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    output.with_suffix('.fpk.sha256').write_text(sha256(output) + '  ' + output.name + '\n', encoding='utf-8')
    print('Built', output)


if __name__ == '__main__':
    main()
