import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from scripts import build


def write_png(path, size):
    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data)))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress((b'\0' + b'\0\0\0\xff' * size) * size))
                     + chunk(b'IEND', b''))


class PackageTests(unittest.TestCase):
    def test_package_icons_support_old_and_new_upstream_layouts(self):
        for layout in ('legacy', 'current'):
            for arch, platform in [('amd64', 'x86'), ('arm64', 'arm')]:
                with self.subTest(layout=layout, arch=arch), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    source = root / 'source'
                    icon64 = source / ('internal/gui/icon.png' if layout == 'legacy'
                                       else 'build/windows/icon-64.png')
                    icon256 = source / 'internal/gui/icon-256.png'
                    write_png(icon64, 64)
                    write_png(icon256, 256)
                    (source / 'LICENSE').write_text('upstream license', encoding='utf-8')
                    (source / 'THIRD_PARTY_NOTICES').write_text('notices', encoding='utf-8')
                    binary = root / 'magpie'
                    binary.write_bytes(b'binary fixture')
                    destination = root / 'package'
                    build.prepare_package(source, binary, destination, arch, '1.0.1', {})
                    for original, packaged, ui in [(icon64, 'ICON.PNG', 'icon_64.png'),
                                                    (icon256, 'ICON_256.PNG', 'icon_256.png')]:
                        self.assertEqual((destination / packaged).read_bytes(), original.read_bytes())
                        self.assertEqual((destination / 'app/ui/images' / ui).read_bytes(),
                                         original.read_bytes())
                    self.assertIn('platform=' + platform + '\n',
                                  (destination / 'manifest').read_text(encoding='utf-8'))
                    self.assertEqual((destination / 'app/bin/magpie').read_bytes(), b'binary fixture')
                    info = json.loads((destination / 'app/build-info.json').read_text(encoding='utf-8'))
                    self.assertEqual(info['architecture'], arch)


if __name__ == '__main__':
    unittest.main()
