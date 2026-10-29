"""官方预编译包的固定输入与更新身份；不把 nightly 时间当作版本。"""
import hashlib
import io
import re
import stat
import urllib.parse
import urllib.request
import zipfile

MAX_ARCHIVE=256*1024*1024
MAX_PAYLOAD=512*1024*1024
OFFICIAL_HOSTS={'buildbot.libretro.com'}

class PinnedArchiveChanged(ValueError):
    pass


def validate_url(value, hosts=OFFICIAL_HOSTS):
    url=urllib.parse.urlparse(value)
    if (url.scheme!='https' or url.hostname not in hosts or url.port not in (None,443)
            or url.username or url.password or url.fragment):
        raise ValueError('来源必须是登记的官方 HTTPS 地址')
    return value


class Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts): self.hosts=hosts
    def redirect_request(self,request,fp,code,message,headers,newurl):
        validate_url(newurl,self.hosts)
        return super().redirect_request(request,fp,code,message,headers,newurl)


def fetch(value, hosts=OFFICIAL_HOSTS, limit=MAX_ARCHIVE):
    validate_url(value,hosts)
    opener=urllib.request.build_opener(Redirects(hosts))
    with opener.open(urllib.request.Request(value,headers={'User-Agent':'Continue-Core-Release'}),timeout=60) as response:
        data=response.read(limit+1)
    if len(data)>limit: raise ValueError('下载大小超限')
    return data


def inspect_zip(data, member):
    if len(data)>MAX_ARCHIVE: raise ValueError('下载包超限')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries=archive.infolist()
        names=[e.filename for e in entries]
        if names!=[member] or member.startswith('/') or '..' in member.split('/') or '\\' in member:
            raise ValueError('ZIP 成员与登记内容不符')
        entry=entries[0]
        if entry.file_size>MAX_PAYLOAD or stat.S_ISLNK(entry.external_attr >> 16):
            raise ValueError('ZIP 成员类型或大小不符')
        payload=archive.read(member)
    return {'archive_sha256':hashlib.sha256(data).hexdigest(),
            'payload_sha256':hashlib.sha256(payload).hexdigest(),'payload':payload}


def revision(version):
    found=re.search(r'(?:\bg|git[- ]?)([0-9a-f]{7,40})(?:\b|$)',version,re.I)
    if not found:
        # mGBA 的版本描述省略 git describe 默认的 g 前缀。
        found=re.search(r'-\d+-([0-9a-f]{7,40})(?:-dirty)?$',version,re.I)
    return found.group(1).lower() if found else None


def base_version(value):
    found=re.match(r'^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?',value)
    if not found: raise ValueError('无法识别预编译 Core 版本')
    return '.'.join(str(int(x or 0)) for x in found.groups())


def resource_version(value):
    base=base_version(value); commit=revision(value)
    return base+'-snapshot'+('.'+commit if commit else '')


def classify(previous, observed):
    if previous is None: return 'initial'
    try:
        before=tuple(map(int,base_version(previous.get('version','')).split('.')))
        after=tuple(map(int,base_version(observed.get('version','')).split('.')))
    except ValueError:
        return 'unchanged' if previous.get('payload_sha256')==observed.get('payload_sha256') else 'candidate'
    if after>before: return 'update'
    if after<before: return 'candidate'
    old,new=previous.get('revision'),observed.get('revision')
    if old and new:
        same=old.lower().startswith(new.lower()) or new.lower().startswith(old.lower())
        return 'unchanged' if same else 'update'
    if previous.get('payload_sha256')==observed.get('payload_sha256'): return 'unchanged'
    return 'candidate'


def describe(url, member):
    value=inspect_zip(fetch(url),member)
    return {k:v for k,v in value.items() if k!='payload'} | {'url':url,'member':member}


def retrieve(description):
    result=inspect_zip(fetch(description['url']),description['member'])
    if any(result[key]!=description[key] for key in ['archive_sha256','payload_sha256']):
        raise PinnedArchiveChanged('上游包在准备后已变化，请重新生成输入锁')
    return result['payload']


def file_description(url, hosts=OFFICIAL_HOSTS):
    data=fetch(url,hosts)
    return {'url':url,'archive_sha256':hashlib.sha256(data).hexdigest()}


def retrieve_file(description,hosts=OFFICIAL_HOSTS):
    data=fetch(description['url'],hosts)
    if hashlib.sha256(data).hexdigest()!=description['archive_sha256']:
        raise PinnedArchiveChanged('上游包在准备后已变化，请重新生成输入锁')
    return data


def runtime_assets(data, destination):
    result={}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if len(archive.infolist())>8192: raise ValueError('资源条目超限')
        if sum(i.file_size for i in archive.infolist())>MAX_PAYLOAD: raise ValueError('资源展开大小超限')
        for entry in archive.infolist():
            name=entry.filename
            if name.startswith('/') or '..' in name.split('/') or '\\' in name or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('资源路径或类型不安全')
            if entry.is_dir(): continue
            if name.startswith('PPSSPP/'): name=name[len('PPSSPP/'):]
            if '.git' in name.split('/') or name.endswith('.gitignore'): continue
            path=destination+'/'+name
            if path in result: raise ValueError('资源路径重复')
            result[path]=archive.read(entry)
    return result
