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
