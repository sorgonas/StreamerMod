"""Discover used managed assemblies with the installed Roslyn compiler."""
import asyncio
import hashlib
import json
import re
from pathlib import Path
from xml.sax.saxutils import escape
from .core import ActionError
from .csharp import dotnet_path,dotnet_env,stop_process,injected_source,checked_references,_locks


def version_key(path):return tuple(int(n) for n in re.findall(r'\d+',path.name))


async def analyzer(root,tool="FindRefs"):
    installation=Path(dotnet_path()).resolve().parent
    sdks=sorted((installation/'sdk').glob('*'),key=version_key)
    if not sdks:raise ActionError('.NET SDK fehlt')
    roslyn=sdks[-1]/'Roslyn/bincore'
    code=Path(__file__).with_name('csharp_host').joinpath(tool+'.cs').read_text()
    directory=Path(root)/'state/csharp-tools'/hashlib.sha256((code+str(roslyn)).encode()).hexdigest()
    dll=directory/('out/'+tool+'.dll')
    lock=_locks.setdefault(str(directory),asyncio.Lock())
    async with lock:
        if dll.exists():return dll
        directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
        (directory/(tool+'.cs')).write_text(code)
        refs=''.join('<Reference Include="'+name+'"><HintPath>'+escape(str(roslyn/(name+'.dll')))+'</HintPath></Reference>' for name in ['Microsoft.CodeAnalysis','Microsoft.CodeAnalysis.CSharp'])
        (directory/(tool+'.csproj')).write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup>'+refs+'</ItemGroup></Project>')
        process=await asyncio.create_subprocess_exec(dotnet_path(),'build',str(directory/(tool+'.csproj')),'-o',str(directory/'out'),'-v','quiet','--nologo',env=dotnet_env(),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        try:output,_=await asyncio.wait_for(process.communicate(),90)
        except BaseException:
            await stop_process(process);raise
        if process.returncode:raise ActionError('Referenzanalyse konnte nicht erstellt werden: '+output.decode(errors='replace')[-3000:])
    return dll


async def find_references(root,code,references=None):
    selected=checked_references(references)
    installation=Path(dotnet_path()).resolve().parent
    packs=sorted((installation/'packs/Microsoft.NETCore.App.Ref').glob('*'),key=version_key)
    if not packs:raise ActionError('.NET Referenzbibliotheken fehlen')
    framework=sorted((packs[-1]/'ref/net10.0').glob('*.dll'))
    if not framework:raise ActionError('.NET 10 Referenzbibliotheken fehlen')
    libraries=Path(root)/'csharp-libraries'
    local=sorted(libraries.rglob('*.dll')) if libraries.is_dir() else []
    selected_names={p.name for p in selected}
    local=[p for p in local if p.name not in selected_names]
    # Explicit references take priority over same-named files in the discovery folder.
    paths=list(dict.fromkeys([*framework,*selected,*local]))
    dll=await analyzer(root)
    host=Path(__file__).with_name('csharp_host').joinpath('Bridge.cs').read_text()
    source='global using System; global using System.Collections.Generic; global using System.IO; global using System.Linq; global using System.Threading; global using System.Threading.Tasks;\n'+injected_source(code)
    process=await asyncio.create_subprocess_exec(dotnet_path(),str(dll),env=dotnet_env(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:
        output,error=await asyncio.wait_for(process.communicate(json.dumps({'source':source,'host':host,'paths':[str(p.resolve()) for p in paths]}).encode()),30)
    except BaseException:
        await stop_process(process);raise
    try:result=json.loads(output)
    except ValueError:raise ActionError('Referenzanalyse fehlgeschlagen: '+error.decode(errors='replace')[-1000:]) from None
    if result.get('error'):raise ActionError('Referenzanalyse: '+result['error'])
    builtins={str(p.resolve()) for p in framework}
    found=[{'name':Path(p).name,'path':p,'kind':'Framework' if p in builtins else 'Local DLL'} for p in result.get('references',[])]
    additions=[entry['path'] for entry in found if entry['kind']=='Local DLL']
    return {'references':found,'selected':list(dict.fromkeys([*(str(p) for p in selected),*additions])),
            'diagnostics':result.get('diagnostics',[])+result.get('rejected',[])}


async def format_code(root,code,indent=4):
    if indent not in (2,4,8):raise ActionError('Einrückung muss 2, 4 oder 8 Leerzeichen betragen')
    dll=await analyzer(root,'FormatCode')
    process=await asyncio.create_subprocess_exec(dotnet_path(),str(dll),env=dotnet_env(),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:output,error=await asyncio.wait_for(process.communicate(json.dumps({'code':code,'indent':indent}).encode()),30)
    except BaseException:
        await stop_process(process);raise
    if process.returncode:raise ActionError('Formatierung fehlgeschlagen: '+error.decode(errors='replace')[-1000:])
    return json.loads(output)['code']
