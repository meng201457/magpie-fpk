import copy
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from scripts import check_upstream as sync


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        self.lock = {'repository': 'yetone/magpie', 'version': 'v0.1.9',
                     'commit': 'a' * 40, 'package_version': '1.0.0',
                     'fnpack': {'version': '1.2.3'}}
        self.release = {'tag_name': 'v0.1.10', 'draft': False, 'prerelease': False}

    def test_new_release_pins_commit_and_increments_package(self):
        updated = sync.resolve_lock(self.lock, self.release, 'b' * 40)
        self.assertEqual(updated['version'], 'v0.1.10')
        self.assertEqual(updated['commit'], 'b' * 40)
        self.assertEqual(updated['package_version'], '1.0.1')
        self.assertEqual(self.lock['version'], 'v0.1.9')
        self.assertEqual(updated['fnpack'], self.lock['fnpack'])

    def test_same_release_keeps_package_version(self):
        self.release['tag_name'] = 'v0.1.9'
        self.assertEqual(sync.resolve_lock(self.lock, self.release, 'a' * 40), self.lock)

    def test_older_release_does_not_downgrade(self):
        self.release['tag_name'] = 'v0.1.8'
        self.assertEqual(sync.resolve_lock(self.lock, self.release, 'b' * 40), self.lock)

    def test_drafts_and_prereleases_are_ignored(self):
        for flag in ('draft', 'prerelease'):
            release = self.release | {flag: True}
            self.assertEqual(sync.resolve_lock(self.lock, release, 'b' * 40), self.lock)

    def test_retagged_release_is_rejected(self):
        self.release['tag_name'] = 'v0.1.9'
        with self.assertRaises(ValueError):
            sync.resolve_lock(self.lock, self.release, 'b' * 40)

    def test_invalid_tags_and_commits_are_rejected(self):
        for tag, commit in [('v0.1.10-rc1', 'b' * 40), ('v0.1.10', 'main')]:
            with self.subTest(tag=tag, commit=commit), self.assertRaises(ValueError):
                sync.resolve_lock(self.lock, self.release | {'tag_name': tag}, commit)

    def test_missing_or_partial_release_requires_retry(self):
        self.assertFalse(sync.release_complete(None, '1.0.0'))
        assets = [{'name': 'magpie-1.0.0-' + arch + suffix, 'state': 'uploaded', 'size': 123}
                  for arch in ('x86', 'arm64')
                  for suffix in ('.fpk', '.fpk.sha256', '.build-info.json')]
        release = {'draft': False, 'prerelease': False, 'assets': assets}
        self.assertTrue(sync.release_complete(release, '1.0.0'))
        incomplete = copy.deepcopy(release)
        incomplete['assets'].pop()
        self.assertFalse(sync.release_complete(incomplete, '1.0.0'))
        for field, value in [('size', 0), ('state', 'starter')]:
            broken = copy.deepcopy(release)
            broken['assets'][0][field] = value
            self.assertFalse(sync.release_complete(broken, '1.0.0'))
        self.assertFalse(sync.release_complete(release | {'draft': True}, '1.0.0'))

    def test_command_writes_resolved_lock_and_build_output(self):
        responses = {
            'yetone/magpie/releases/latest': self.release,
            'yetone/magpie/commits/v0.1.10': {'sha': 'b' * 40},
            'example/packages/releases/tags/fpk-v1.0.1': None,
        }
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'lock.json'
            output = Path(directory) / 'output.txt'
            lock.write_text(json.dumps(self.lock), encoding='utf-8')
            with patch.object(sys, 'argv', ['check_upstream.py', '--lock', str(lock)]), \
                    patch.dict(os.environ, {'GITHUB_REPOSITORY': 'example/packages',
                                            'GITHUB_SHA': 'd' * 40,
                                            'GITHUB_OUTPUT': str(output)}), \
                    patch.object(sync, 'github_api', side_effect=lambda path, **kw: responses[path]):
                sync.main()
            updated = json.loads(lock.read_text(encoding='utf-8'))
            self.assertEqual(updated['commit'], 'b' * 40)
            self.assertEqual(updated['package_version'], '1.0.1')
            self.assertEqual(output.read_text(encoding='utf-8'),
                             'should_build=true\nsource_ref=' + 'd' * 40 + '\n')

    def test_retry_uses_existing_package_tag_source(self):
        responses = {
            'yetone/magpie/releases/latest': self.release | {'tag_name': 'v0.1.9'},
            'yetone/magpie/commits/v0.1.9': {'sha': 'a' * 40},
            'example/packages/releases/tags/fpk-v1.0.0': None,
            'example/packages/commits/fpk-v1.0.0': {'sha': 'c' * 40},
        }
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'lock.json'
            output = Path(directory) / 'output.txt'
            lock.write_text(json.dumps(self.lock), encoding='utf-8')
            with patch.object(sys, 'argv', ['check_upstream.py', '--lock', str(lock)]), \
                    patch.dict(os.environ, {'GITHUB_REPOSITORY': 'example/packages',
                                            'GITHUB_SHA': 'd' * 40,
                                            'GITHUB_OUTPUT': str(output)}), \
                    patch.object(sync, 'github_api', side_effect=lambda path, **kw: responses[path]):
                sync.main()
            self.assertEqual(output.read_text(encoding='utf-8'),
                             'should_build=true\nsource_ref=' + 'c' * 40 + '\n')

    def test_api_failure_does_not_change_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            lock = Path(directory) / 'lock.json'
            original = json.dumps(self.lock)
            lock.write_text(original, encoding='utf-8')
            with patch.object(sys, 'argv', ['check_upstream.py', '--lock', str(lock)]), \
                    patch.object(sync, 'github_api', side_effect=OSError('API unavailable')):
                with self.assertRaises(OSError):
                    sync.main()
            self.assertEqual(lock.read_text(encoding='utf-8'), original)

    def test_only_optional_404_is_treated_as_missing(self):
        for code, optional in [(404, False), (403, True), (500, True)]:
            error = urllib.error.HTTPError('https://api.github.com', code, 'error', {}, None)
            with self.subTest(code=code, optional=optional), \
                    patch.object(sync.urllib.request, 'urlopen', side_effect=error):
                with self.assertRaises(urllib.error.HTTPError):
                    sync.github_api('example/packages/releases/tags/fpk-v1.0.0', missing_ok=optional)
        error = urllib.error.HTTPError('https://api.github.com', 404, 'missing', {}, None)
        with patch.object(sync.urllib.request, 'urlopen', side_effect=error):
            self.assertIsNone(sync.github_api('example/packages/releases/tags/fpk-v1.0.0', missing_ok=True))


if __name__ == '__main__':
    unittest.main()
