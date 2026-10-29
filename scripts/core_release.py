#!/usr/bin/env python3
"""正式上游 Release → 固定 SHA → 原生 libretro → 不可覆盖的 Cart Release。"""
import argparse
import ctypes
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / 'registry/mgba.json').read_text())
TARGETS = REGISTRY['targets']
CART_ID = 'org.continue.core.mgba'
RESOURCE_ID = 'org.continue.resource.core.mgba'
STABLE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
RECIPE_FILES = ('scripts/core_release.py', 'registry/mgba.json', 'mise.toml', '.github/workflows/release.yml')
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$')

class ReleaseError(Exception):
    pass

def require(condition, message):
    if not condition:
        raise ReleaseError(message)

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def digest(data):
    return hashlib.sha256(data).hexdigest()

def run(args, cwd=None):
    completed = subprocess.run(list(map(str, args)), cwd=cwd, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise ReleaseError(f'命令失败 ({completed.returncode}): {args[0]}\n{completed.stdout[-12000:]}')
    return completed.stdout.strip()

def api(path, method='GET', body=None, missing_ok=False):
    url = 'https://api.github.com/' + path.lstrip('/')
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28',
               'User-Agent': 'Continue-Core-Release'}
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        raise ReleaseError(f'GitHub API 失败: HTTP {error.code}: {path}') from error
    except (OSError, ValueError) as error:
        raise ReleaseError(f'GitHub API 网络或解析失败: {path}: {error}') from error

def pages(path):
    result = []
    for page in range(1, 1001):
        batch = api(f'{path}?per_page=100&page={page}')
        require(isinstance(batch, list), 'GitHub 列表响应格式错误')
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise ReleaseError('GitHub 分页超过安全限制')

def resolve_tag(tag):
    repo = REGISTRY['upstream_repo']
    ref = api(f'repos/{repo}/git/ref/tags/{urllib.parse.quote(tag, safe="")}')['object']
    for _ in range(8):
        if ref['type'] == 'commit':
            require(re.fullmatch('[0-9a-f]{40}', ref['sha']), '来源 SHA 格式错误')
            return ref['sha']
        require(ref['type'] == 'tag', '正式 tag 未指向 commit')
        ref = api(f'repos/{repo}/git/tags/{ref["sha"]}')['object']
    raise ReleaseError('tag 解引用层数超限')

def version_tuple(tag):
    require(STABLE.fullmatch(tag), '正式版本格式错误')
    return tuple(map(int, tag.split('.')))

def select_candidate(releases, adopted, resolver):
    # 先审计所有已采用 tag，旧 tag 被移动也必须报错。
    for prior in adopted:
        require(resolver(prior['tag']) == prior['sha'], f'已采用 tag 移动: {prior["tag"]}')
    newest = max((version_tuple(p['tag']) for p in adopted), default=(-1, -1, -1))
    candidates = [r for r in releases if not r['draft'] and not r['prerelease']
                  and STABLE.fullmatch(r['tag_name']) and version_tuple(r['tag_name']) > newest]
    if not candidates:
        return None
    # 每轮只采用最新正式版；长期未运行时不为过时版本制造新 Cart。
    tag = max(candidates, key=lambda r: version_tuple(r['tag_name']))['tag_name']
    return {'tag': tag, 'sha': resolver(tag)}

def published_sources():
    sources = []
    repo = REGISTRY['release_repo']
    for release in pages(f'repos/{repo}/releases'):
        if release['draft'] or not release['tag_name'].startswith('mgba/v'):
            continue
        assets = [a for a in release['assets'] if a['name'] == 'release-report.json']
        require(len(assets) == 1, f'发布缺失持久来源账本: {release["tag_name"]}')
        # 只读本仓固定资产地址，不采用可由上游描述注入的 URL。
        url = f'https://github.com/{repo}/releases/download/{release["tag_name"]}/release-report.json'
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                report = json.load(response)
        except (OSError, ValueError) as error:
            raise ReleaseError('持久发布账本读取失败') from error
        require(report['lock']['source']['repo'] == REGISTRY['upstream_repo'], '账本来源不符')
        sources.append({**report['lock']['source'], 'cart_version':report['lock']['cart_version']})
    return sources

def cart_version_key(value):
    require(SEMVER.fullmatch(value), 'Cart 账本 SemVer 无效')
    base, _, pre = value.partition('-')
    identifiers = tuple((0, int(x)) if x.isdigit() else (1, x) for x in pre.split('.')) if pre else ()
    require(not pre or all(x and (not x.isdigit() or x == '0' or not x.startswith('0')) for x in pre.split('.')), 'Cart prerelease 无效')
    return (*map(int, base.split('.')), 0 if pre else 1, identifiers)


def allocate_cart_version(adopted):
    if not adopted:
        return REGISTRY['bootstrap']['cart_version']
    latest = max((p['cart_version'] for p in adopted), key=cart_version_key)
    major, minor, patch, stable, _ = cart_version_key(latest)
    return f'{major}.{minor}.{patch + 1 if stable else patch}'


def require_recipe_checkout(lock, root=ROOT):
    root = Path(root)
    require(run(['git', 'rev-parse', 'HEAD'], root) == lock['recipe']['commit'], '配方 commit 与输入锁不符')
    require(not run(['git', 'status', '--porcelain', '--untracked-files=no'], root), '配方工作区已有未提交改动')
    for name, expected in lock['recipe']['files'].items():
        require(sha256(root/name) == expected, f'配方文件摘要不符: {name}')
        committed = subprocess.run(['git', 'show', f'HEAD:{name}'], cwd=root, stdout=subprocess.PIPE, check=True).stdout
        require(digest(committed) == expected, f'配方文件与提交内容不符: {name}')


def make_lock(tag, sha, cart_version, recipe_commit):
    lock = {'schema': 'continue.core-release.v1', 'cart_id': CART_ID,
            'resource_id': RESOURCE_ID, 'cart_version': cart_version,
            'release_tag': 'mgba/v' + cart_version,
            'source': {'repo': REGISTRY['upstream_repo'], 'tag': tag, 'version': tag, 'sha': sha},
            'recipe': {'revision': REGISTRY['recipe_revision'], 'commit': recipe_commit,
                       'cmake_options': REGISTRY['cmake_options'],
                       'files':{name:sha256(ROOT/name) for name in RECIPE_FILES}},
            'targets': TARGETS}
    validate_lock(lock)
    return lock

def validate_lock(lock):
    require(lock['cart_id'] == CART_ID and lock['resource_id'] == RESOURCE_ID, '锁定身份不符')
    source = lock['source']
    require(source['repo'] == REGISTRY['upstream_repo'] and STABLE.fullmatch(source['tag'])
            and source['version'] == source['tag'] and re.fullmatch('[0-9a-f]{40}', source['sha']), '来源锁定无效')
    if source['tag'] == REGISTRY['bootstrap']['tag']:
        require(source['sha'] == REGISTRY['bootstrap']['sha'], '来源与已审计 bootstrap SHA 不符')
    require(SEMVER.fullmatch(lock['cart_version']), 'Cart 版本必须是 SemVer')
    require(lock['release_tag'] == 'mgba/v' + lock['cart_version'], '发布 tag 不符')
    require(lock['targets'] == TARGETS, '目标集合不符')
    require(lock['recipe']['cmake_options'] == REGISTRY['cmake_options']
            and lock['recipe']['revision'] == REGISTRY['recipe_revision']
            and re.fullmatch('[0-9a-f]{40}', lock['recipe']['commit'])
            and set(lock['recipe']['files']) == set(RECIPE_FILES)
            and all(re.fullmatch('[0-9a-f]{64}', h) for h in lock['recipe']['files'].values()), '构建配方不符')

def prepare(tag, cart_version, output):
    release = api(f'repos/{REGISTRY["upstream_repo"]}/releases/tags/{tag}')
    require(not release['draft'] and not release['prerelease'] and STABLE.fullmatch(tag), '只接受上游正式 Release')
    commit = run(['git', 'rev-parse', 'HEAD'], ROOT)
    require(not run(['git', 'status', '--porcelain', '--untracked-files=no'], ROOT), '准备发布前必须提交配方改动')
    lock = make_lock(tag, resolve_tag(tag), cart_version, commit)
    require_recipe_checkout(lock)
    prior = published_sources()
    require(not prior or cart_version_key(cart_version) > max(cart_version_key(p['cart_version']) for p in prior), '新 Cart 版本必须大于所有已发布版本')
    write_json(output, lock)
    return lock

def native_target():
    machine = platform.machine().lower()
    arch = {'arm64': 'aarch64', 'aarch64': 'aarch64', 'amd64': 'x86_64', 'x86_64': 'x86_64'}.get(machine, machine)
    system = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}.get(platform.system())
    return f'{system}-{arch}'

def binary_target(data):
    if data[:4] == b'\xcf\xfa\xed\xfe' and len(data) >= 16:
        cpu = struct.unpack_from('<I', data, 4)[0]
        return 'macos-aarch64' if cpu == 0x0100000c else 'macos-x86_64'
    if data[:4] == b'\x7fELF' and len(data) >= 20 and data[4:6] == b'\x02\x01':
        return 'linux-x86_64' if struct.unpack_from('<H', data, 18)[0] == 62 else 'linux-unknown'
    if data[:2] == b'MZ' and len(data) > 64:
        offset = struct.unpack_from('<I', data, 60)[0]
        if data[offset:offset+4] == b'PE\0\0' and len(data) >= offset+6:
            return 'windows-x86_64' if struct.unpack_from('<H', data, offset+4)[0] == 0x8664 else 'windows-unknown'
    raise ReleaseError('不能识别二进制目标')

def extension(target):
    return { 'macos': 'dylib', 'linux': 'so', 'windows': 'dll'}[target.split('-')[0]]

def package(lock, target, binary, license_path, evidence, output):
    validate_lock(lock)
    require(target in TARGETS, '未知目标')
    data = Path(binary).read_bytes()
    require(binary_target(data) == target, '二进制目标与 Cart 目标不符')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    system, arch = target.split('-')
    filename = f'mgba-{lock["cart_version"]}-{target}.cart'
    entry = f'targets/{target}/mgba.{extension(target)}'
    manifest = f'''schema = "continue.cartfile.v1"
id = "{CART_ID}"
name = "mGBA Core"
version = "{lock['cart_version']}"
author = "mGBA Contributors"
publisher = "Continue"
description = "由 Continue 从 mGBA 正式源码构建的 libretro core。"
[artifact]
format = "cart.zip.v1"
[artifact.target]
os = "{system}"
arch = "{arch}"
[include]
paths = ["cores/", "LICENSE", "SOURCE.md", "build-report.json"]
'''
    resource = f'''schema = "continue.resource.v1"
type = "core"
id = "{RESOURCE_ID}"
name = "mGBA"
version = "{lock['source']['version']}"
author = "mGBA Contributors"
license = "MPL-2.0"
description = "正式版 mGBA，Continue 源码构建。"
[entrypoints]
{system}_{arch} = "{entry}"
[[targets]]
os = "{system}"
arch = "{arch}"
[core]
platforms = ["gba", "gbc", "gb"]
'''
    source = lock['source']
    source_text = f'''# mGBA 对应源码与许可\n\n上游：https://github.com/{source['repo']}\n正式 tag：{source['tag']}\n完整 commit：{source['sha']}\n对应源码：https://github.com/{source['repo']}/tree/{source['sha']}\n下载归档：https://github.com/{source['repo']}/archive/{source['sha']}.tar.gz\n本次 Release 另附 mgba-source-{source['sha']}.tar.gz（git archive 原始源码与第三方许可）。\n\n构建配方：https://github.com/{REGISTRY['release_repo']}/tree/{lock['recipe']['commit']}\n本包未修改上游源文件。mGBA 采用 MPL-2.0；完整许可见 LICENSE。\n嵌入第三方源码与各自许可保留在对应源码归档 src/third-party 与 include 目录。\nContinue 的打包脚本采用 MIT，不改变上游许可。\n\n禁用外部可选依赖：FFmpeg、zlib、PNG、zip、SQLite、Lua、LZMA、调试器及前端。\n本配方针对未压缩 ROM；不承诺被禁用功能或完整模拟器 UI。\n原生 ABI 检查不代表实际 ROM、图像、音频、输入或性能验收。\n'''
    build_report = {'lock': lock, 'target': target, 'binary_sha256': digest(data),
                    'binary_size_bytes': len(data), 'evidence': evidence}
    files = {'cartfile.toml': manifest.encode(), 'cores/mgba/continue.toml': resource.encode(),
             'cores/mgba/' + entry: data, 'LICENSE': Path(license_path).read_bytes(),
             'SOURCE.md': source_text.encode(),
             'build-report.json': (json.dumps(build_report, indent=2, ensure_ascii=False)+'\n').encode()}
    path = output / filename
    require(not path.exists(), '拒绝覆盖本地已有 Cart；请使用新的输出目录')
    # 固定容器元数据；原生编译仍受已记录的工具链和系统环境影响。
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    report = {**build_report, 'file': filename, 'sha256': sha256(path), 'size_bytes': path.stat().st_size}
    verify_package(path, report, lock)
    write_json(output / f'{target}.report.json', report)
    write_json(output / 'input-lock.json', lock)
    return report

def verify_package(path, report, lock):
    validate_lock(lock)
    require(Path(report['file']).name == report['file'], '包名不安全')
    require(path.stat().st_size == report['size_bytes'], 'Cart 大小不符')
    require(sha256(path) == report['sha256'], 'Cart 摘要不符')
    require(report['lock'] == lock, '逐包锁定来源不符')
    target = report['target']
    require(target in lock['targets'], '包目标不符')
    system, arch = target.split('-')
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'ZIP 含重复路径')
        require(all(not n.startswith('/') and '..' not in n.split('/') and '\\' not in n for n in names), 'ZIP 路径不安全')
        manifest = tomllib.loads(archive.read('cartfile.toml').decode())
        resource = tomllib.loads(archive.read('cores/mgba/continue.toml').decode())
        require(manifest['schema'] == 'continue.cartfile.v1' and manifest['id'] == CART_ID
                and manifest['version'] == lock['cart_version'], 'Cart 身份不符')
        require(manifest['artifact'] == {'format': 'cart.zip.v1', 'target': {'os':system, 'arch':arch}}, 'Cart 目标不符')
        require(resource['schema'] == 'continue.resource.v1' and resource['type'] == 'core'
                and resource['id'] == RESOURCE_ID and resource['version'] == lock['source']['version'], '资源身份不符')
        entry = f'targets/{target}/mgba.{extension(target)}'
        require(resource['entrypoints'] == {f'{system}_{arch}': entry}
                and resource['targets'] == [{'os':system, 'arch':arch}], '资源目标或入口不符')
        data = archive.read('cores/mgba/' + entry)
        require(binary_target(data) == target, '二进制目标不符')
        require(digest(data) == report['binary_sha256'] and len(data) == report['binary_size_bytes'], '二进制摘要或大小不符')
        inner = json.loads(archive.read('build-report.json'))
        require(inner == {k: report[k] for k in ('lock', 'target', 'binary_sha256', 'binary_size_bytes', 'evidence')}, '内外构建报告不一致')
        require(lock['source']['sha'] in archive.read('SOURCE.md').decode()
                and b'Mozilla Public License' in archive.read('LICENSE'), '来源或许可缺失')
        expected = {'cartfile.toml', 'cores/mgba/continue.toml', 'cores/mgba/' + entry,
                    'LICENSE', 'SOURCE.md', 'build-report.json'}
        require(set(names) == expected, '包内出现未登记文件')
    return report

def verify_source_archive(archive_path, lock, reports):
    expected = {'file':archive_path.name, 'sha256':sha256(archive_path), 'size_bytes':archive_path.stat().st_size}
    require(all(r['evidence'].get('source_archive') == expected for r in reports), '源码归档与逐目标构建报告摘要不符')
    try:
        with tarfile.open(archive_path, 'r:gz') as archive:
            members = archive.getmembers()
            names = [m.name for m in members]
            require(len(names) == len(set(names)) and len(names) < 100000, '源码归档路径重复或过多')
            require(all((m.name == 'mgba' or m.name.startswith('mgba/')) and '..' not in m.name.split('/')
                        and '\\' not in m.name and (m.isfile() or m.isdir()) for m in members), '源码归档路径或类型不安全')
            require(archive.pax_headers.get('comment') == lock['source']['sha'], '源码归档 commit 身份不符')
            required = ['mgba/version.cmake', 'mgba/CMakeLists.txt', 'mgba/LICENSE',
                        'mgba/src/third-party/inih/LICENSE.txt', 'mgba/src/third-party/blip_buf/license.txt']
            require(all(name in names for name in required), '源码归档缺少正式构建源码或许可')
            require(sum(m.size for m in members) <= 1024*1024*1024, '源码归档展开大小超限')
            version_file = archive.extractfile('mgba/version.cmake').read().decode()
            actual = '.'.join(re.search(r'set\(LIB_VERSION_' + part + r'\s+(\d+)\)', version_file)[1] for part in ('MAJOR', 'MINOR', 'PATCH'))
            require(actual == lock['source']['version'], '源码归档 Core 版本身份不符')
            require(b'Mozilla Public License' in archive.extractfile('mgba/LICENSE').read(), '源码归档许可不符')
    except (tarfile.TarError, OSError, KeyError, AttributeError, TypeError) as error:
        raise ReleaseError('源码归档格式或身份无效') from error
    return expected


def verify_release(directory):
    directory = Path(directory)
    lock = json.loads((directory / 'input-lock.json').read_text())
    validate_lock(lock)
    reports = [json.loads(p.read_text()) for p in sorted(directory.glob('*.report.json'))]
    require(len(reports) == len(TARGETS) and {r['target'] for r in reports} == set(TARGETS), '发布目标集合不完整或重复')
    for report in reports:
        verify_package(directory / report['file'], report, lock)
    require({p.name for p in directory.glob('*.cart')} == {r['file'] for r in reports}, '存在未登记 Cart')
    archive = directory / f'mgba-source-{lock["source"]["sha"]}.tar.gz'
    require(archive.is_file(), '发布缺失对应源码归档')
    summary = {'schema': 'continue.core-release-report.v1', 'lock': lock, 'artifacts': reports,
               'source_archive': verify_source_archive(archive, lock, reports)}
    existing = directory / 'release-report.json'
    if existing.exists():
        require(json.loads(existing.read_text()) == summary, '已有全发布报告与当前输入不符')
    write_json(existing, summary)
    names = sorted([r['file'] for r in reports] + [archive.name, 'input-lock.json', 'release-report.json']
                   + [p.name for p in directory.glob('*.report.json')])
    checksum = ''.join(f'{sha256(directory / name)}  {name}\n' for name in names)
    (directory / 'SHA256SUMS').write_text(checksum, encoding='utf-8')
    return summary

def abi_probe(binary):
    library = ctypes.CDLL(str(Path(binary).resolve()))
    # 全套 libretro 必需入口必须可解析；只调用无宿主回调依赖的查询入口。
    symbols = ('retro_init retro_deinit retro_api_version retro_get_system_info retro_get_system_av_info '
               'retro_set_environment retro_set_video_refresh retro_set_audio_sample retro_set_audio_sample_batch '
               'retro_set_input_poll retro_set_input_state retro_set_controller_port_device retro_reset retro_run '
               'retro_serialize_size retro_serialize retro_unserialize retro_cheat_reset retro_cheat_set '
               'retro_load_game retro_load_game_special retro_unload_game retro_get_region '
               'retro_get_memory_data retro_get_memory_size').split()
    for symbol in symbols:
        getattr(library, symbol)
    require(library.retro_api_version() == 1, 'libretro API 版本不符')
    class SystemInfo(ctypes.Structure):
        _fields_ = [('library_name', ctypes.c_char_p), ('library_version', ctypes.c_char_p),
                    ('valid_extensions', ctypes.c_char_p), ('need_fullpath', ctypes.c_bool),
                    ('block_extract', ctypes.c_bool)]
    info = SystemInfo()
    library.retro_get_system_info(ctypes.byref(info))
    return {'retro_api_version': 1, 'library_name': info.library_name.decode(),
            'library_version': info.library_version.decode(), 'valid_extensions': info.valid_extensions.decode(),
            'exported_symbols': symbols}

def validate_macos_dependencies(listing, install_name):
    dependencies = [line.strip().split(' (')[0] for line in listing.splitlines()[1:]]
    require(all(d == install_name or d.startswith('/usr/lib/') or d.startswith('/System/Library/')
                for d in dependencies), 'macOS 非系统动态依赖')


def native_dependencies(binary, target):
    if target.startswith('macos'):
        listing = run(['otool', '-L', binary])
        install_names = run(['otool', '-D', binary]).splitlines()[1:]
        require(len(install_names) == 1, 'macOS install name 不唯一')
        validate_macos_dependencies(listing, install_names[0].strip())
        return listing
    if target.startswith('linux'):
        listing = run(['ldd', binary])
        require('not found' not in listing, 'Linux 动态依赖缺失')
        names = [line.strip().split()[0] for line in listing.splitlines() if line.strip()]
        allowed = re.compile(r'^(linux-vdso|lib(c|m|pthread|dl|rt|gcc_s)\.so|/lib\S*/ld-linux)')
        require(all(allowed.match(n) for n in names), 'Linux 非预期动态依赖: ' + listing)
        return listing
    listing = run(['dumpbin', '/dependents', binary])
    dlls = re.findall(r'^\s+([\w.-]+\.dll)\s*$', listing, re.M | re.I)
    require(all(re.fullmatch(r'(kernel32|user32|advapi32|shell32|ole32|ws2_32|bcrypt|ntdll|ucrtbase|api-ms-win-[\w-]+)\.dll', d, re.I) for d in dlls), 'Windows 非系统动态依赖: ' + listing)
    return listing

def archive_source(source, output):
    # Git for Windows 的全局 autocrlf 也会影响 git archive；显式使用原始 blob 换行。
    run(['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', '-C', source,
         'archive', '--format=tar.gz', '--prefix=mgba/', '--output', Path(output).resolve(), 'HEAD'])


def build(lock_path, target, output):
    lock = json.loads(Path(lock_path).read_text())
    validate_lock(lock)
    require(native_target() == target, f'必须在对应原生目标构建: 本机 {native_target()}, 请求 {target}')
    require_recipe_checkout(lock)
    require(resolve_tag(lock['source']['tag']) == lock['source']['sha'], '准备后来源 tag 移动')
    work = ROOT / 'work' / target
    require(not work.exists(), '构建目录已存在；请显式移除 work 后重试')
    work.mkdir(parents=True)
    source = work / 'source'
    run(['git', 'init', source])
    run(['git', '-C', source, 'remote', 'add', 'origin', 'https://github.com/' + REGISTRY['upstream_repo'] + '.git'])
    run(['git', '-C', source, 'fetch', '--depth=1', 'origin', lock['source']['sha']])
    run(['git', '-C', source, 'config', 'core.autocrlf', 'false'])
    run(['git', '-C', source, 'config', 'core.eol', 'lf'])
    run(['git', '-C', source, 'checkout', '--detach', 'FETCH_HEAD'])
    require(run(['git', '-C', source, 'rev-parse', 'HEAD']) == lock['source']['sha'], '实际源码 SHA 不符')
    build_dir = work / 'build'
    options = [f'-D{k}={v}' for k, v in lock['recipe']['cmake_options'].items()]
    options += ['-DSKIP_GIT=ON', f'-DGIT_TAG={lock["source"]["tag"]}', f'-DGIT_COMMIT={lock["source"]["sha"]}']
    if target.startswith('windows'):
        options += ['-G', 'Visual Studio 17 2022', '-A', 'x64', '-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded',
                    '-DCMAKE_POLICY_DEFAULT_CMP0091=NEW']
    else:
        options += ['-G', 'Unix Makefiles']
    if target.startswith('macos'):
        options += ['-DCMAKE_OSX_ARCHITECTURES=arm64', '-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0']
    configure_log = run(['cmake', '-S', source, '-B', build_dir, *options])
    build_log = run(['cmake', '--build', build_dir, '--config', 'Release', '--target', 'mgba_libretro', '--parallel', '3'])
    candidates = list(build_dir.rglob('*libretro.' + extension(target)))
    require(len(candidates) == 1, '无法确定唯一 libretro 构建输出')
    binary = candidates[0]
    require(binary_target(binary.read_bytes()) == target, '构建输出架构不符')
    abi = abi_probe(binary)
    require(abi['library_name'].lower() == 'mgba' and abi['library_version'].startswith(lock['source']['version']), '原生 Core 版本不符')
    evidence = {'platform': platform.platform(), 'machine': platform.machine(),
                'runner_image': os.environ.get('ImageVersion', 'local'),
                'python': sys.version, 'cmake': run(['cmake', '--version']),
                'compiler': '\n'.join(p.read_text() for p in sorted(build_dir.rglob('CMakeCCompiler.cmake'))),
                'dependencies': native_dependencies(binary, target), 'abi': abi,
                'cmake_cache': (build_dir / 'CMakeCache.txt').read_text(),
                'configure_log': configure_log, 'build_log': build_log}
    if target.startswith('macos'):
        evidence['sdk'] = run(['xcrun', '--show-sdk-version'])
        evidence['binary_load_commands'] = run(['otool', '-l', binary])
    if target.startswith('linux'):
        evidence['symbol_versions'] = run(['readelf', '--version-info', binary])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    archive = output / f'mgba-source-{lock["source"]["sha"]}.tar.gz'
    archive_source(source, archive)
    evidence['source_archive'] = {'file':archive.name, 'sha256':sha256(archive), 'size_bytes':archive.stat().st_size}
    license_bundle = work / 'LICENSE'
    notice_paths = [source/'LICENSE', source/'src/third-party/inih/LICENSE.txt',
                    source/'src/third-party/blip_buf/license.txt']
    license_bundle.write_text('\n\n'.join(f'=== {p.relative_to(source)} ===\n{p.read_text()}' for p in notice_paths)
                              + '\n\nblip-buf Copyright (C) 2003-2009 Shay Green. LGPL-2.1-or-later.\n', encoding='utf-8')
    return package(lock, target, binary, license_bundle, evidence, output)

def validate_publication(existing, expected):
    if existing is None:
        return sorted(expected)
    require(existing['draft'], '拒绝覆盖已公开 Release（包括试运行 prerelease）')
    assets = existing['assets']
    require(len({a['name'] for a in assets}) == len(assets), 'Draft 资产重复')
    for asset in assets:
        require(asset['name'] in expected and asset.get('digest') == 'sha256:' + expected[asset['name']],
                '拒绝覆盖已有 Draft 资产；摘要不符或不受支持')
    return sorted(set(expected) - {a['name'] for a in assets})

def publish(directory):
    directory = Path(directory)
    summary = verify_release(directory)
    lock = summary['lock']
    require_recipe_checkout(lock)
    repo = REGISTRY['release_repo']
    tag = lock['release_tag']
    # 发布只接受有明确发布保护的平台；每次真正发布前再次审计来源。
    require(resolve_tag(lock['source']['tag']) == lock['source']['sha'], '发布前来源 tag 移动')
    files = sorted(p for p in directory.iterdir() if p.is_file())
    expected_names = {a['file'] for a in summary['artifacts']} | {a['target']+'.report.json' for a in summary['artifacts']}
    expected_names |= {'input-lock.json', 'release-report.json', 'SHA256SUMS', summary['source_archive']['file']}
    require({p.name for p in files} == expected_names, '发布目录有未登记文件')
    expected = {p.name: sha256(p) for p in files}
    adopted = published_sources()
    require(not adopted or cart_version_key(lock['cart_version']) > max(cart_version_key(p['cart_version']) for p in adopted), '新 Cart 版本必须大于所有已发布版本，拒绝覆盖或降级')
    existing = api(f'repos/{repo}/releases/tags/{urllib.parse.quote(tag, safe="")}', missing_ok=True)
    missing = validate_publication(existing, expected)
    if existing is None:
        # 拒绝复用游离 tag，防止发布指向错误配方。
        prior_tag = api(f'repos/{repo}/git/ref/tags/{urllib.parse.quote(tag, safe="")}', missing_ok=True)
        require(prior_tag is None, '发布 tag 已存在但没有可恢复 Draft')
        notes = (f'mGBA {lock["source"]["version"]}（正式源码 {lock["source"]["sha"]}）\n\n'
                 f'Continue Cart {lock["cart_version"]}；原生 ABI 检查通过，未进行 ROM/图像/音频/性能验收。\n'
                 '三个目标、源码与全部校验材料先收齐，再公开。详见 release-report.json 与 SOURCE.md。')
        existing = api(f'repos/{repo}/releases', 'POST', {'tag_name':tag, 'target_commitish':lock['recipe']['commit'],
                      'name':f'mGBA {lock["source"]["version"]} / Cart {lock["cart_version"]}',
                      'body':notes, 'draft':True, 'prerelease':'-' in lock['cart_version']})
    for name in missing:
        run(['gh', 'release', 'upload', tag, directory/name, '--repo', repo])
    remote = api(f'repos/{repo}/releases/{existing["id"]}')
    require(validate_publication(remote, expected) == [], 'Draft 未收齐全部资产')
    # 不使用 --clobber；GitHub 不可变 Release 发布后由平台锁定。
    result = api(f'repos/{repo}/releases/{existing["id"]}', 'PATCH', {'draft':False, 'make_latest':'false' if '-' in lock['cart_version'] else 'true'})
    require(result.get('immutable') is True, '发布未获得 GitHub immutable 保护；请检查仓库设置')
    return {'release_url':result['html_url'], 'immutable':result['immutable']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('check')
    check.add_argument('core', choices=['mgba'])
    check.add_argument('--output', default='candidate.json')
    prep = sub.add_parser('prepare')
    prep.add_argument('core', choices=['mgba'])
    prep.add_argument('version')
    prep.add_argument('--cart-version')
    prep.add_argument('--output', default='input-lock.json')
    builder = sub.add_parser('build')
    builder.add_argument('input_lock')
    builder.add_argument('target', choices=TARGETS)
    builder.add_argument('--output', default='dist')
    for command in ('verify', 'publish'):
        p = sub.add_parser(command)
        p.add_argument('directory')
    args = parser.parse_args()
    try:
        if args.command == 'check':
            adopted = published_sources()
            candidate = select_candidate(pages(f'repos/{REGISTRY["upstream_repo"]}/releases'), adopted, resolve_tag)
            result = {'update': candidate is not None, 'candidate':candidate}
            if candidate:
                result['cart_version'] = allocate_cart_version(adopted)
            write_json(args.output, result)
            if os.environ.get('GITHUB_OUTPUT'):
                with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
                    output.write(f'update={str(result["update"]).lower()}\n')
                    if candidate:
                        output.write(f'version={candidate["tag"]}\ncart_version={result["cart_version"]}\n')
        elif args.command == 'prepare':
            cart = args.cart_version or allocate_cart_version(published_sources())
            result = prepare(args.version, cart, args.output)
        elif args.command == 'build':
            result = build(args.input_lock, args.target, args.output)
        elif args.command == 'verify':
            result = verify_release(args.directory)
        else:
            result = publish(args.directory)
        printable = {k: result[k] for k in ('file', 'sha256', 'size_bytes', 'target', 'binary_sha256')} if args.command == 'build' else result
        print(json.dumps(printable, indent=2, ensure_ascii=False))
    except (ReleaseError, OSError, KeyError, ValueError, zipfile.BadZipFile) as error:
        print(f'core-release: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
