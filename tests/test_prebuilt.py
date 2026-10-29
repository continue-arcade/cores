"""预编译优先、固定包身份和不追逐例行 nightly 的更新判断。"""
import importlib.util
import io
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/prebuilt.py'
module=None
if SCRIPT.exists():
 spec=importlib.util.spec_from_file_location('prebuilt',SCRIPT);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class HybridTests(unittest.TestCase):
 def setUp(self): self.assertIsNotNone(module,'尚未实现预编译供应路径')
 def test_update_uses_version_or_revision_instead_of_zip_or_payload_rebuild(self):
  old={'version':'1.20.4','revision':'abcdef1234','payload_sha256':'a'}
  self.assertEqual(module.classify(old,dict(old,archive_sha256='different')),'unchanged')
  self.assertEqual(module.classify(old,dict(old,payload_sha256='rebuild')),'unchanged')
  self.assertEqual(module.classify(old,dict(old,version='1.20.5')),'update')
  self.assertEqual(module.classify(old,dict(old,revision='fedcba4321')),'update')
  unknown={'version':'115','revision':None,'payload_sha256':'a'}
  self.assertEqual(module.classify(unknown,dict(unknown,payload_sha256='b')),'candidate')
  self.assertEqual(module.classify(None,unknown),'initial')
 def test_exact_zip_member_and_uncompressed_payload_are_pinned(self):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z: z.writestr('core.dylib',b'fixed binary')
  actual=module.inspect_zip(out.getvalue(),'core.dylib')
  self.assertEqual(actual['payload'],b'fixed binary')
  self.assertEqual(len(actual['payload_sha256']),64)
  with self.assertRaisesRegex(ValueError,'成员'): module.inspect_zip(out.getvalue(),'other.dylib')
 def test_archive_rejects_duplicate_unsafe_and_extra_members(self):
  for names in [['../core.dylib'],['core.dylib','unexpected'],['core.dylib','core.dylib']]:
   out=io.BytesIO()
   with zipfile.ZipFile(out,'w') as z:
    for name in names: z.writestr(name,b'bytes')
   with self.assertRaises(ValueError): module.inspect_zip(out.getvalue(),'core.dylib')
 def test_snapshot_version_is_explicit_and_embedded_revision_is_preserved(self):
  self.assertEqual(module.resource_version('v1.20.4-31-gabcdef1234'),'1.20.4-snapshot.abcdef1234')
  self.assertEqual(module.resource_version('115'),'115.0.0-snapshot')
  self.assertEqual(module.revision('v1.20.4-31-gabcdef1234'),'abcdef1234')
  self.assertEqual(module.revision('0.11-212-7a12d6d'),'7a12d6d')
 def test_only_registered_official_https_locations_are_accepted(self):
  for value in ['http://buildbot.libretro.com/core.zip','https://user:secret@buildbot.libretro.com/core.zip','https://buildbot.libretro.com.evil.org/core.zip']:
   with self.assertRaises(ValueError): module.validate_url(value)
  module.validate_url('https://buildbot.libretro.com/nightly/linux/x86_64/latest/mgba_libretro.so.zip')
 def test_pinned_latest_changes_fail_instead_of_silently_replacing_input(self):
  def archive(body):
   out=io.BytesIO()
   with zipfile.ZipFile(out,'w') as z: z.writestr('core.dylib',body)
   return out.getvalue()
  original=archive(b'original');replacement=archive(b'rebuilt')
  description=module.inspect_zip(original,'core.dylib')
  description.pop('payload');description.update(url='https://buildbot.libretro.com/core.zip',member='core.dylib')
  with patch.object(module,'fetch',return_value=original): self.assertEqual(module.retrieve(description),b'original')
  with patch.object(module,'fetch',return_value=replacement):
   with self.assertRaises(module.PinnedArchiveChanged): module.retrieve(description)

class PrebuiltReleaseTests(unittest.TestCase):
 def test_forced_prebuilt_without_input_never_silently_builds_source(self):
  script=Path(__file__).resolve().parents[1]/'scripts/core_release.py'
  spec=importlib.util.spec_from_file_location('forced_prebuilt_pipeline',script);pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
  lock=pipeline.make_lock('0.10.5',pipeline.REGISTRY['bootstrap']['sha'],'0.2.0','a'*40,supply='prebuilt')
  with self.assertRaisesRegex(pipeline.ReleaseError,'强制预编译'): pipeline.build_prebuilt(lock,'macos-aarch64','unused')
 def test_pinned_archive_change_does_not_trigger_source_fallback(self):
  import json
  script=Path(__file__).resolve().parents[1]/'scripts/core_release.py'
  spec=importlib.util.spec_from_file_location('pinned_prebuilt_pipeline',script);pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
  lock=pipeline.make_lock('0.10.5',pipeline.REGISTRY['bootstrap']['sha'],'0.2.0','a'*40,supply='auto')
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'lock.json';path.write_text(json.dumps(lock))
   with patch.object(pipeline,'native_target',return_value='macos-aarch64'),patch.object(pipeline,'require_recipe_checkout'),patch.object(pipeline,'resolve_tag',return_value=lock['source']['sha']),patch.object(pipeline,'build_prebuilt',side_effect=pipeline.prebuilt.PinnedArchiveChanged('changed')),patch.object(pipeline,'run') as runner:
    with self.assertRaises(pipeline.prebuilt.PinnedArchiveChanged): pipeline.build(path,'macos-aarch64',Path(directory)/'out')
    runner.assert_not_called()
 def test_prebuilt_release_needs_no_reference_source_archive(self):
  import importlib.util,struct,json
  script=Path(__file__).resolve().parents[1]/'scripts/core_release.py'
  spec=importlib.util.spec_from_file_location('prebuilt_pipeline',script);pipeline=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipeline)
  pipeline.select_core('mgba')
  lock=pipeline.make_lock('0.10.5',pipeline.REGISTRY['bootstrap']['sha'],'0.2.0','a'*40)
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);license_file=root/'LICENSE';license_file.write_text('Mozilla Public License Version 2.0')
   for target in pipeline.TARGETS:
    if target.startswith('macos'): data=struct.pack('<IIII',0xfeedfacf,0x0100000c,0,6)+b'\0'*48
    elif target.startswith('linux'):
     data=bytearray(64);data[:6]=b'\x7fELF\x02\x01';struct.pack_into('<H',data,18,62);data=bytes(data)
    else:
     data=bytearray(128);data[:2]=b'MZ';struct.pack_into('<I',data,60,64);data[64:68]=b'PE\0\0';struct.pack_into('<H',data,68,0x8664);data=bytes(data)
    binary=root/'binary';binary.write_bytes(data)
    origin={'url':pipeline.prebuilt_location(target)[0],'archive_sha256':'c'*64,'payload_sha256':pipeline.digest(data),'version':'0.10.5','revision':None,'upstream_source_url':'https://github.com/libretro/mgba'}
    evidence={'supply_kind':'prebuilt','binary_origin':origin,'resource_version':'0.10.5-snapshot','abi':{'library_version':'0.10.5'},'source_archive':None}
    pipeline.package(lock,target,binary,license_file,evidence,root/'out')
    with zipfile.ZipFile(root/'out'/f'mgba-{lock["cart_version"]}-{target}.cart') as archive:
     self.assertNotIn('正式源码构建',archive.read('cartfile.toml').decode())
     self.assertIn('预编译快照',archive.read('cores/mgba/continue.toml').decode())
   summary=pipeline.verify_release(root/'out')
   self.assertIsNone(summary['source_archive'])
   self.assertNotIn('source-',(root/'out/SHA256SUMS').read_text())
