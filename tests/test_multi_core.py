"""多 Core 的隔离身份、正式 tag 及运行资源回归。"""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('multi_release', Path(__file__).resolve().parents[1] / 'scripts/core_release.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


class MultiCoreTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(core, 'select_core'):
            core.select_core('mgba')

    def test_each_core_has_independent_cart_identity_and_release_prefix(self):
        self.assertTrue(hasattr(core, 'select_core'), '流水线仍只支持 mGBA')
        for slug in ['mgba', 'mesen', 'bsnes', 'ppsspp']:
            core.select_core(slug)
            registry = core.REGISTRY
            lock = core.make_lock(registry['bootstrap']['tag'], registry['bootstrap']['sha'], '0.1.0-smoke.1', 'a'*40)
            self.assertEqual(lock['cart_id'], 'org.continue.core.' + slug)
            self.assertEqual(lock['resource_id'], 'org.continue.resource.core.' + slug)
            self.assertEqual(lock['release_tag'], slug + '/v0.1.0-smoke.1')

    def test_official_single_component_and_v_prefixed_versions_are_normalized(self):
        self.assertTrue(hasattr(core, 'select_core'), '缺少每 Core 正式 tag 策略')
        for slug, tag, version in [('bsnes','v115','115.0.0'), ('ppsspp','v1.20.4','1.20.4'), ('mesen','0.9.9','0.9.9')]:
            core.select_core(slug)
            lock = core.make_lock(tag, core.REGISTRY['bootstrap']['sha'], '0.1.0-smoke.1', 'a'*40)
            self.assertEqual(lock['source']['version'], version)
            releases = [{'tag_name':tag,'draft':False,'prerelease':False},
                        {'tag_name':'nightly','draft':False,'prerelease':False},
                        {'tag_name':tag+'-dev','draft':False,'prerelease':True}]
            candidate = core.select_candidate(releases, [], lambda _: core.REGISTRY['bootstrap']['sha'])
            self.assertEqual(candidate['tag'],tag)

    def test_unknown_core_and_path_traversal_are_rejected(self):
        self.assertTrue(hasattr(core, 'select_core'))
        for slug in ['../mgba', 'other', 'mgba/../../secret']:
            with self.assertRaises(core.ReleaseError):
                core.select_core(slug)

    def test_ppsspp_declares_complete_runtime_assets_mapping(self):
        self.assertTrue(hasattr(core, 'select_core'))
        core.select_core('ppsspp')
        self.assertEqual(core.REGISTRY['runtime_assets'], {'source':'assets','destination':'system/PPSSPP'})
        self.assertIn('flash0/font', core.REGISTRY['required_runtime_assets'])
        self.assertIn('compat.ini', core.REGISTRY['required_runtime_assets'])
        self.assertIn('ppge_atlas.zim', core.REGISTRY['required_runtime_assets'])

class RuntimePackageTests(unittest.TestCase):
    def tearDown(self):
        core.select_core('mgba')

    def test_ppsspp_package_binds_runtime_bytes_and_rejects_tampering(self):
        import struct,zipfile,hashlib
        core.select_core('ppsspp')
        lock=core.make_lock('v1.20.4',core.REGISTRY['bootstrap']['sha'],'0.1.0-smoke.1','a'*40)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            binary=root/'core.dylib'; binary.write_bytes(struct.pack('<IIII',0xfeedfacf,0x0100000c,0,6)+b'\0'*48)
            license_file=root/'LICENSE';license_file.write_text('GNU GENERAL PUBLIC LICENSE')
            assets={'cores/ppsspp/system/PPSSPP/'+p:b'fixed '+p.encode() for p in ['compat.ini','flash0/font/font.pgf','ppge_atlas.zim','ppge_atlas.meta']}
            with self.assertRaisesRegex(core.ReleaseError,'运行资源'):
                core.package(lock,'macos-aarch64',binary,license_file,{},root/'missing')
            report=core.package(lock,'macos-aarch64',binary,license_file,{},root/'out',assets)
            path=root/'out'/report['file']
            with zipfile.ZipFile(path) as archive:
                files={name:archive.read(name) for name in archive.namelist()}
                resource=core.tomllib.loads(files['cores/ppsspp/continue.toml'].decode())
                self.assertEqual(resource['core']['system_directory'],'system')
                self.assertEqual(files['cores/ppsspp/system/PPSSPP/compat.ini'],b'fixed compat.ini')
            files['cores/ppsspp/system/PPSSPP/compat.ini']=b'tampered runtime data'
            with zipfile.ZipFile(path,'w') as archive:
                for name,data in files.items(): archive.writestr(name,data)
            report['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();report['size_bytes']=path.stat().st_size
            with self.assertRaisesRegex(core.ReleaseError,'运行资源摘要'):
                core.verify_package(path,report,lock)

    def test_corresponding_source_archive_contains_fixed_submodules(self):
        import subprocess,tarfile
        core.select_core('ppsspp')
        def git(root,*args):
            return subprocess.check_output(['git','-C',str(root),'-c','user.name=Test','-c','user.email=test@example.com',*args],text=True).strip()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source';child=root/'child'
            for path in [source,child]:
                path.mkdir();git(path,'init','-q');(path/'README.txt').write_text(path.name+'\n');git(path,'add','.');git(path,'commit','-qm','fixture')
            git(source,'-c','protocol.file.allow=always','submodule','add',str(child),'ext/fixed')
            git(source,'commit','-qam','pin submodule')
            archive=root/'source.tar.gz';core.archive_source(source,archive)
            with tarfile.open(archive) as packed:
                self.assertEqual(packed.extractfile('ppsspp/ext/fixed/README.txt').read(),b'child\n')
                self.assertEqual(packed.pax_headers['comment'],git(source,'rev-parse','HEAD'))

class WorkflowIdentityTests(unittest.TestCase):
    def tearDown(self):
        core.select_core('mgba')

    def test_requested_core_must_match_downloaded_input_lock(self):
        core.select_core('ppsspp')
        lock=core.make_lock('v1.20.4',core.REGISTRY['bootstrap']['sha'],'0.1.0-smoke.1','a'*40)
        with self.assertRaisesRegex(core.ReleaseError,'Core.*不符'):
            core.activate_lock(lock,'mesen')
