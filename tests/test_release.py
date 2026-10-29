"""发布策略与真实 ZIP 包验证；不依赖网络或产品仓库。"""
import copy
import importlib.util
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/core_release.py'
if SCRIPT.exists():
    spec = importlib.util.spec_from_file_location('core_release', SCRIPT)
    core = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(core)
else:
    core = None

SHA = '26b7884bc25a5933960f3cdcd98bac1ae14d42e2'
TARGETS = ['macos-aarch64', 'windows-x86_64', 'linux-x86_64']

def release(tag, **kwargs):
    return {'tag_name': tag, 'draft': False, 'prerelease': False, **kwargs}

class ReleasePolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(core, '固定发布脚本尚未实现')

    def test_only_new_stable_release_is_candidate(self):
        releases = [release('0.10.5'), release('0.11.0-beta', prerelease=True),
                    release('nightly'), release('0.10.6', draft=True), release('0.9.9')]
        result = core.select_candidate(releases, [], lambda tag: SHA)
        self.assertEqual(result['tag'], '0.10.5')
        self.assertEqual(result['sha'], SHA)
        self.assertIsNone(core.select_candidate(releases, [result], lambda tag: SHA))

    def test_previously_adopted_version_blocks_downgrade(self):
        self.assertIsNone(core.select_candidate([release('0.9.9')],
                         [{'tag': '0.10.5', 'sha': SHA}], lambda tag: SHA))

    def test_moved_old_tag_fails_even_when_new_version_exists(self):
        with self.assertRaisesRegex(core.ReleaseError, '移动'):
            core.select_candidate([release('0.10.6')], [{'tag': '0.10.5', 'sha': SHA}],
                                  lambda tag: 'a' * 40)

    def test_network_failure_never_means_no_updates(self):
        def failed(_tag):
            raise OSError('network unavailable')
        with self.assertRaises(OSError):
            core.select_candidate([release('0.10.5')], [], failed)

    def test_published_release_is_never_overwritten(self):
        with self.assertRaisesRegex(core.ReleaseError, '覆盖'):
            core.validate_publication({'draft': False, 'assets': []}, {'a.cart': '1' * 64})

    def test_draft_conflicting_assets_are_not_overwritten(self):
        existing = {'draft': True, 'assets': [{'name': 'a.cart', 'digest': 'sha256:' + '2'*64}]}
        with self.assertRaisesRegex(core.ReleaseError, '覆盖'):
            core.validate_publication(existing, {'a.cart': '1'*64})
        existing['assets'][0]['digest'] = 'sha256:' + '1'*64
        self.assertEqual(core.validate_publication(existing, {'a.cart': '1'*64}), [])

class DependencyTests(unittest.TestCase):
    def test_macos_install_name_is_not_an_external_dependency(self):
        listing = 'core:\n\tmgba_libretro.dylib (compatibility version 0.0.0)\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)'
        self.assertIsNotNone(core)
        self.assertTrue(hasattr(core, 'validate_macos_dependencies'), '尚未区分自身 install name')
        core.validate_macos_dependencies(listing, 'mgba_libretro.dylib')

    def test_macos_homebrew_dependency_is_rejected(self):
        self.assertIsNotNone(core)
        self.assertTrue(hasattr(core, 'validate_macos_dependencies'), '尚未区分自身 install name')
        with self.assertRaisesRegex(core.ReleaseError, '非系统'):
            core.validate_macos_dependencies('core:\n\t/opt/homebrew/lib/libz.dylib (compatibility version 1.0.0)', 'mgba_libretro.dylib')

class PackageTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(core, '固定发布脚本尚未实现')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.lock = core.make_lock('0.10.5', SHA, '0.1.0-smoke.1', 'a'*40)
        self.license = self.root / 'LICENSE'
        self.license.write_text('Mozilla Public License Version 2.0\n')
        # 真实容器头供目标核验；原生 ABI 冒烟由 build 执行。
        self.binary = self.root / 'mgba.dylib'
        self.binary.write_bytes(struct.pack('<IIII', 0xfeedfacf, 0x0100000c, 0, 6) + b'\0'*48)
        self.evidence = {'compiler': 'fixture compiler', 'dependencies': 'fixture system only',
                         'abi': {'retro_api_version': 1}, 'cmake_cache': 'fixture'}

    def package(self):
        return core.package(self.lock, 'macos-aarch64', self.binary, self.license,
                            self.evidence, self.root / 'out')

    def test_package_has_independent_cart_resource_versions_and_full_provenance(self):
        report = self.package()
        path = self.root / 'out' / report['file']
        core.verify_package(path, report, self.lock)
        with zipfile.ZipFile(path) as cart:
            manifest = core.tomllib.loads(cart.read('cartfile.toml').decode())
            resource = core.tomllib.loads(cart.read('cores/mgba/continue.toml').decode())
            self.assertEqual(manifest['id'], 'org.continue.core.mgba')
            self.assertEqual(manifest['version'], '0.1.0-smoke.1')
            self.assertEqual(manifest['artifact']['target'], {'os':'macos', 'arch':'aarch64'})
            self.assertEqual(resource['version'], '0.10.5')
            self.assertEqual(resource['id'], 'org.continue.resource.core.mgba')
            self.assertIn(SHA, cart.read('SOURCE.md').decode())
            self.assertIn('LICENSE', cart.namelist())

    def test_tampered_cart_is_rejected(self):
        report = self.package()
        path = self.root / 'out' / report['file']
        with path.open('ab') as output:
            output.write(b'tampered')
        with self.assertRaisesRegex(core.ReleaseError, '摘要|大小'):
            core.verify_package(path, report, self.lock)

    def test_wrong_target_cannot_be_packaged(self):
        with self.assertRaisesRegex(core.ReleaseError, '目标'):
            core.package(self.lock, 'linux-x86_64', self.binary, self.license,
                         self.evidence, self.root / 'out')

    def test_manifest_identity_tampering_is_rejected_even_with_updated_outer_hash(self):
        report = self.package()
        path = self.root / 'out' / report['file']
        with zipfile.ZipFile(path) as archive:
            files = {n: archive.read(n) for n in archive.namelist()}
        files['cartfile.toml'] = files['cartfile.toml'].replace(b'org.continue.core.mgba', b'org.evil.core.mgba')
        with zipfile.ZipFile(path, 'w') as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        report['sha256'] = core.sha256(path)
        report['size_bytes'] = path.stat().st_size
        with self.assertRaisesRegex(core.ReleaseError, '身份'):
            core.verify_package(path, report, self.lock)

    def test_incomplete_release_cannot_be_published(self):
        self.package()
        core.write_json(self.root/'out/input-lock.json', self.lock)
        with self.assertRaisesRegex(core.ReleaseError, '目标集合'):
            core.verify_release(self.root/'out')

    def test_complete_release_requires_source_and_generates_persistent_audit(self):
        import hashlib
        out = self.root / 'out'
        self.package()
        elf = bytearray(64)
        elf[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', elf, 18, 62)
        pe = bytearray(128)
        pe[:2] = b'MZ'
        struct.pack_into('<I', pe, 60, 64)
        pe[64:68] = b'PE\0\0'
        struct.pack_into('<H', pe, 68, 0x8664)
        for target, data in [('linux-x86_64', elf), ('windows-x86_64', pe)]:
            self.binary.write_bytes(data)
            core.package(self.lock, target, self.binary, self.license, self.evidence, out)
        with self.assertRaisesRegex(core.ReleaseError, '源码归档'):
            core.verify_release(out)
        archive = out / f'mgba-source-{SHA}.tar.gz'
        archive.write_bytes(b'fixture source archive')
        result = core.verify_release(out)
        self.assertEqual({r['target'] for r in result['artifacts']}, set(TARGETS))
        self.assertEqual(result['source_archive']['sha256'], hashlib.sha256(b'fixture source archive').hexdigest())
        self.assertEqual(json.loads((out/'release-report.json').read_text())['lock']['source']['sha'], SHA)
        self.assertIn('release-report.json', (out/'SHA256SUMS').read_text())
        archive.write_bytes(b'changed source archive')
        with self.assertRaisesRegex(core.ReleaseError, '全发布报告'):
            core.verify_release(out)

    def test_source_pin_cannot_be_mutated(self):
        lock = copy.deepcopy(self.lock)
        lock['source']['sha'] = 'b'*40
        with self.assertRaisesRegex(core.ReleaseError, '来源'):
            core.validate_lock(lock)

if __name__ == '__main__':
    unittest.main()
