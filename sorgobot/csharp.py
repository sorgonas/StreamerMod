"""Compile real C# and run CPHInline in a separate process with an async RPC bridge."""
import asyncio
import hashlib
import json
import os
import re
import shutil
from xml.sax.saxutils import escape
from pathlib import Path
from .core import ActionError,StopAction,walk

DEFAULT_CODE='''using System;

public class CPHInline
{
    public bool Execute()
    {
        CPH.TryGetArg<string>("user", out var user);
        CPH.SetArgument("csharpResult", "Hallo " + user);
        return true;
    }
}
'''


def dotnet_path():
    local=Path(__file__).resolve().parents[1]/'runtimes/dotnet/dotnet'
    return str(local) if local.is_file() else shutil.which('dotnet') or str(Path.home()/'.local/share/sorgobot-dotnet/dotnet')


def dotnet_env():
    return {**os.environ,'DOTNET_CLI_TELEMETRY_OPTOUT':'1','DOTNET_NOLOGO':'1','DOTNET_SKIP_FIRST_TIME_EXPERIENCE':'1'}


async def stop_process(process):
    if process.returncode is None:
        try:process.kill()
        except ProcessLookupError:pass
    await process.wait()


def injected_source(code):
    match=re.search(r'\bclass\s+CPHInline\b[^\{]*\{',code)
    if not match:raise ActionError('C# benötigt eine Klasse CPHInline mit public bool Execute().')
    return code[:match.end()]+'\npublic SorgobotCPH CPH { get; set; } = null!;\npublic System.Collections.Generic.Dictionary<string,object?> args => CPH.args;\n'+code[match.end():]


def checked_references(references):
    paths=[]
    for value in references or []:
        path=Path(value).expanduser().resolve()
        if not path.is_file() or path.suffix.casefold()!='.dll':raise ActionError('C#-Referenz fehlt oder ist keine DLL: '+str(path))
        if path not in paths:paths.append(path)
    return paths


def reference_fingerprint(paths):
    digest=hashlib.sha256()
    for path in paths:
        digest.update(str(path).encode())
        with path.open('rb') as stream:
            while chunk:=stream.read(512*1024):digest.update(chunk)
    return digest.hexdigest()


async def compile_code(root,code,references=None):
    dotnet=dotnet_path()
    if not Path(dotnet).is_file():raise ActionError('C# benötigt das .NET SDK. Die lokale Laufzeit fehlt.')
    if not str(code).strip():raise ActionError('C#-Code fehlt')
    host=Path(__file__).with_name('csharp_host').joinpath('Bridge.cs').read_text()
    source=injected_source(code)
    paths=checked_references(references)
    fingerprint=await asyncio.to_thread(reference_fingerprint,paths)
    digest=hashlib.sha256((source+host+fingerprint).encode()).hexdigest()
    directory=Path(root)/'state/csharp-cache'/digest
    dll=directory/'out/Script.dll'
    if dll.exists():return dll
    # Build once per source hash, even when multiple actions arrive together.
    lock=_locks.setdefault(str(directory),asyncio.Lock())
    async with lock:
        if dll.exists():return dll
        directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
        (directory/'Script.cs').write_text(source)
        (directory/'Bridge.cs').write_text(host)
        reference_xml=''.join('<Reference Include="'+escape(p.stem,{'"':'&quot;'})+'"><HintPath>'+escape(str(p))+'</HintPath><Private>true</Private></Reference>' for p in paths)
        (directory/'Script.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup><Compile Include="Script.cs"/><Compile Include="Bridge.cs"/><Using Include="Streamer.bot.Plugin.Interface.Model"/><Using Include="Streamer.bot.Plugin.Interface.Enums"/><Using Include="Streamer.bot.Common.Events"/>'+reference_xml+'</ItemGroup></Project>')
        process=await asyncio.create_subprocess_exec(dotnet,'build',str(directory/'Script.csproj'),'-o',str(directory/'out'),'-v','quiet','--nologo',env=dotnet_env(),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
        try:
            output,_=await asyncio.wait_for(process.communicate(),90)
        except BaseException:
            await stop_process(process);raise
        diagnostics=output.decode(errors='replace')
        (directory/'compile.log').write_text(diagnostics)
        if process.returncode:
            errors=[line.strip() for line in diagnostics.splitlines() if 'error ' in line]
            raise ActionError('C#-Kompilierung fehlgeschlagen: '+'\n'.join(errors[:6])[:3000])
        return dll


_locks={}


async def rpc(engine,method,values):
    if method=='parse_math':
        from .dotnet_values import math_value
        return await asyncio.to_thread(math_value,str(values[0]),str(values[1]),False,str(values[2]) if len(values)>2 and values[2] is not None else 'G')
    if method in ('code_register','code_event','credits'):
        from .csharp_core_services import rpc as services_rpc
        return await services_rpc(engine,method,values)
    if method in ('platform_var','platform_vars_list','platform_vars_bulk'):
        from .csharp_platform_globals import rpc as platform_rpc
        return await platform_rpc(engine,method,values)
    if method in ('keyboard_press','toast','custom_event','reset_first_words','auth_property','legacy_user_unset'):
        from .csharp_system import rpc as system_rpc
        return await system_rpc(engine,method,values)
    if method=='youtube_csharp':
        from .csharp_youtube import rpc as youtube_rpc
        return await youtube_rpc(engine,values)
    if method=='twitch_csharp':
        from .csharp_twitch import rpc as twitch_rpc
        return await twitch_rpc(engine,values)
    if method=='obs_csharp':
        from .csharp_obs import rpc as obs_rpc
        return await obs_rpc(engine,values)
    if method in ('midi_devices','midi_send'):
        from .csharp_midi import rpc as midi_rpc
        return await midi_rpc(engine,method,values)
    if method.startswith('sound_'):
        from .csharp_sounds import rpc as sound_rpc
        return await sound_rpc(engine,method,values)
    if method=='websocket_broadcast':
        from .main_websocket import broadcast_rpc
        return await broadcast_rpc(engine,values)
    if method=='websocket_server':
        from .csharp_custom_server import rpc as server_rpc
        return await server_rpc(engine,values)
    if method=='broadcast_udp':
        from .csharp_udp import broadcast
        return await broadcast(engine,values)
    if method=='websocket_client':
        from .csharp_websocket import rpc as websocket_rpc
        return await websocket_rpc(engine,values)
    if method.startswith('quote_'):
        from .csharp_quotes import rpc as quotes_rpc
        return await quotes_rpc(engine,method,values)
    if method=='runtime_version':
        from .version import runtime_version
        return runtime_version()
    if method=='send':await engine.io.send(str(values[0]),bot=bool(values[1]));return True
    if method=='log':engine.io.trace('log',level=values[0],text=values[1]);return True
    if method=='wait':
        if int(values[0])<0:raise ActionError('C# Wait benötigt mindestens 0 Millisekunden')
        await engine.io.wait(int(values[0])/1000);return True
    if method in ('run','actions_list','action_exists','action_enabled','queue_control','globals_clear'):
        from .csharp_core import rpc as core_rpc
        return await core_rpc(engine,method,values)
    if method in ('globals_list','twitch_var','twitch_vars_list','twitch_vars_bulk','all_users_unset'):
        from .csharp_globals import rpc as globals_rpc
        return await globals_rpc(engine,method,values)
    if method.startswith('command_') or method=='commands_list':
        from .csharp_commands import rpc as command_rpc
        return await command_rpc(engine,method,values)
    if method.startswith('points_'):
        from .csharp_points import rpc as points_rpc
        return await points_rpc(engine,method,values)
    if method.startswith('group_') or method=='groups_list':
        from .csharp_groups import rpc as group_rpc
        return await group_rpc(engine,method,values)
    if method.startswith('timer_'):
        from .timer_control import rpc as timer_rpc
        return await timer_rpc(engine,method,values)
    if method=='execute_method':
        return await execute_method(engine,*values)
    if method.startswith('global_'):
        transient=getattr(engine,'csharp_session_globals',None)
        if transient is None:transient=engine.csharp_session_globals={}
        name=values[0];persisted=bool(values[-1])
        if method=='global_get':return engine.state.get(name) if persisted else transient.get(name)
        if method in ('global_set','global_unset'):
            from .core_events import set_global
            set_global(engine,name,values[1] if method=='global_set' else None,persisted,delete=method=='global_unset')
            return True
    raise ActionError('C#-Bridge-Methode nicht unterstützt: '+method)


async def execute(engine,node,args):
    code_node=node
    method='Execute'
    if node['type']==90061:
        targets=[n for a in engine.actions.values() for n in walk(a.get('subActions',[])) if n.get('type')==90060 and n.get('id')==node.get('codeId')]
        if len(targets)!=1:raise ActionError('Referenzierter C#-Code nicht gefunden oder nicht eindeutig')
        code_node=targets[0];method=node.get('method','Execute')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',method):raise ActionError('Ungültiger C#-Methodenname')
    if node.get('saveResult') and not node.get('resultVariable','').strip():raise ActionError('C# Ergebnisvariable fehlt')
    from .csharp_lifecycle import instances,timeout
    packet=await instances(engine).invoke(code_node,method,args,timeout(node.get('timeout',30)))
    args.update(packet['arguments'])
    if node.get('saveResult'):args[node.get('resultVariable','csharpResult')]=bool(packet['result'])
    elif not packet['result']:raise StopAction('C# Execute hat false zurückgegeben. Hinweise im C#-Log prüfen.')


async def prepare(engine,node):
    from .csharp_lifecycle import instances
    return await instances(engine).prepare(node)


async def reconcile(engine):
    manager=getattr(engine,'csharp_instances',None)
    if manager:await manager.reconcile()


async def shutdown(engine):
    manager=getattr(engine,'csharp_instances',None)
    if manager:await manager.close()


async def precompile(engine,delayed=False):
    for action in list(engine.actions.values()):
        if not action.get('enabled',True):continue
        for node in walk(action.get('subActions',[])):
            if node.get('type')!=90060 or not node.get('enabled',True) or not node.get('precompile') or bool(node.get('delayedStart'))!=delayed:continue
            try:
                await prepare(engine,node)
                engine.io.trace('csharp_precompile',name=node.get('name',''),success=True)
            except (ActionError,OSError,TimeoutError) as error:
                engine.io.trace('csharp_precompile',name=node.get('name',''),success=False,error=str(error))

async def execute_method(engine,execute_code,method_name,arguments,caller):
    if not isinstance(execute_code,str) or not execute_code:raise ActionError('C#-Code-Name fehlt')
    if not isinstance(method_name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',method_name):raise ActionError('Ungültiger C#-Methodenname')
    if getattr(getattr(engine,'studio',None),'closing',False):return {'success':False}
    nodes=[n for a in engine.actions.values() for n in walk(a.get('subActions',[])) if n.get('type')==90060 and n.get('name')==execute_code]
    if len(nodes)>1:raise ActionError('C#-Code-Name ist nicht eindeutig')
    if not nodes:return {'success':False}
    target=nodes[0]
    if target['id']==caller:return {'local':True}
    from .csharp_lifecycle import instances,timeout
    packet=await instances(engine).invoke(target,method_name,arguments,timeout(target.get('timeout',30)))
    return {'success':bool(packet['result']),'arguments':packet['arguments']}
