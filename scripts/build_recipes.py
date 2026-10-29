"""各 Core 的原生构建适配；发布、身份和验包逻辑集中在 core_release。"""
import os
import shutil
from pathlib import Path


def build_native(core, registry, lock, target, source, build_dir, run):
    source, build_dir = Path(source), Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    compiler = 'cl' if target.startswith('windows') else ('clang++' if target.startswith('macos') else os.environ.get('CXX','g++'))
    logs = {'compiler': run([compiler, '--version']) if compiler != 'cl' else os.environ.get('VCToolsInstallDir','MSVC'),
            'configure_log':'', 'cmake_cache':''}
    if core == 'mgba' or (core == 'ppsspp' and not target.startswith('windows')):
        options = [f'-D{k}={v}' for k,v in registry['cmake_options'].items()]
        if core == 'mgba':
            options += ['-DSKIP_GIT=ON',f'-DGIT_TAG={lock["source"]["tag"]}',f'-DGIT_COMMIT={lock["source"]["sha"]}']
        if target.startswith('windows'):
            options += ['-G','Visual Studio 17 2022','-A','x64','-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded','-DCMAKE_POLICY_DEFAULT_CMP0091=NEW']
        else:
            options += ['-G','Unix Makefiles']
        if target.startswith('macos'):
            options += ['-DCMAKE_OSX_ARCHITECTURES=arm64','-DCMAKE_OSX_DEPLOYMENT_TARGET=11.0']
        logs['configure_log']=run(['cmake','-S',source,'-B',build_dir,*options])
        logs['build_log']=run(['cmake','--build',build_dir,'--config','Release','--target',core+'_libretro','--parallel','3'])
        logs['cmake_cache']=(build_dir/'CMakeCache.txt').read_text()
        logs['compiler']='\n'.join(p.read_text() for p in sorted(build_dir.rglob('CMakeCXXCompiler.cmake')))+logs['compiler']
        search=build_dir
    elif core == 'mesen':
        if target.startswith('windows'):
            msbuild=shutil.which('MSBuild.exe') or str(Path(os.environ['VSINSTALLDIR'])/'MSBuild/Current/Bin/MSBuild.exe')
            # Libretro.vcxproj 的依赖在 .sln 中声明；逐项构建三个静态库，保持独立 PCH 目录。
            messages=[]
            for project in ['Core','Utilities','SevenZip','Libretro']:
                messages.append(run([msbuild,source/project/(project+'.vcxproj'),'/m:3','/t:Build','/p:Configuration=Libretro','/p:Platform=x64','/p:PlatformToolset=v143',f'/p:SolutionDir={source}{os.sep}',f'/p:OutDir={build_dir}{os.sep}',f'/p:IntDir={build_dir / "obj" / project}{os.sep}']))
            logs['build_log']='\n'.join(messages)
            search=build_dir
        else:
            args=['make','-C',source/'Libretro','-j3','platform=osx' if target.startswith('macos') else 'platform=unix']
            args += ['ARCHFLAGS=-arch arm64','CC=clang','CXX=clang++'] if target.startswith('macos') else ['CC='+os.environ.get('CC','gcc'),'CXX='+os.environ.get('CXX','g++')]
            logs['build_log']=run(args); search=source/'Libretro'
    elif core == 'bsnes':
        platform_name=target.split('-')[0]
        if target.startswith('windows'):
            mingw=Path('C:/msys64/mingw64/bin')
            os.environ['PATH']=str(mingw)+os.pathsep+os.environ['PATH']
            compiler=str(mingw/'g++.exe')
            logs['compiler']=run([compiler,'--version'])
            compiler += ' -include stdexcept'
        else:
            compiler='clang++ -arch arm64' if target.startswith('macos') else os.environ.get('CXX','g++')+' -include stdexcept'
        logs['build_log']=run(['make','-C',source/'bsnes','-j3','target=libretro','binary=library','local=false','platform='+platform_name,'compiler='+compiler])
        search=source/'bsnes/out'
    elif core == 'ppsspp':
        # 官方 MSVC Make 路径：不引入 CMake 对 libcmt 的排除选项。
        logs['build_log']=run(['make','-C',source/'libretro','-j3','platform=windows_msvc2019_desktop_x64','DEBUG=0','CPUOPTS=-O2 -DNDEBUG -MT'])
        search=source/'libretro'
    else:
        raise ValueError('未支持的构建适配: '+core)
    ext={'macos':'dylib','windows':'dll','linux':'so'}[target.split('-')[0]]
    binaries=list(search.rglob(core+'_libretro.'+ext))
    if len(binaries)!=1:
        raise ValueError('无法找到唯一构建输出: '+str(binaries))
    return binaries[0], logs
