"""Read running executables and map them to configured Twitch categories."""
import re
from pathlib import Path
from .catalog import ConfigStore
from .core import ActionError

def process_name(value):
    return str(value).replace('\\','/').rsplit('/',1)[-1].removesuffix('\x00').casefold().removesuffix('.exe')

def running_processes(proc=Path('/proc')):
    names=set()
    if not proc.is_dir():raise ActionError('Die Spielerkennung benötigt Linux /proc.')
    for directory in proc.iterdir():
        if not directory.name.isdigit():continue
        try:
            args=(directory/'cmdline').read_bytes().decode(errors='replace').split('\0')
            if args and args[0]:names.add(process_name(args[0]))
            # Proton/Wine starts the Windows executable as an argument.
            names.update(process_name(arg) for arg in args[1:] if arg.casefold().endswith('.exe'))
        except (PermissionError,FileNotFoundError,ProcessLookupError):continue
    return names

def detect(document,names,fallback=None):
    for rule in document.get('games',[]):
        if rule.get('process') and rule.get('category') and process_name(rule['process']) in names:
            return {'detectedGame':rule['category'],'detectedProcess':rule['process'],'gameDetected':True,'categorySource':'process'}
    return {'detectedGame':fallback or document.get('fallbackCategory') or 'Just Chatting',
            'detectedProcess':'','gameDetected':False,'categorySource':'fallback'}

def steam_installations(home=None):
    """Read local manifests, including extra Steam libraries; no launcher required."""
    home=Path(home) if home else Path.home()
    roots=[home/'.steam/steam',home/'.local/share/Steam',home/'.var/app/com.valvesoftware.Steam/.local/share/Steam']
    libraries=set()
    for root in roots:
        libraries.add(root.resolve())
        for vdf in [root/'steamapps/libraryfolders.vdf',root/'config/libraryfolders.vdf']:
            try:
                libraries.update(Path(value.replace('\\\\','\\')).resolve() for value in re.findall(r'"path"\s*"([^"\n]+)"',vdf.read_text()))
            except OSError:pass
    games=[]
    for library in sorted(libraries):
        for manifest in sorted((library/'steamapps').glob('appmanifest_*.acf')):
            try:
                fields=dict(re.findall(r'"([^"\n]+)"\s*"([^"\n]*)"',manifest.read_text()))
                name=fields.get('name');folder=fields.get('installdir')
                if name and folder:
                    directory=(library/'steamapps/common'/folder).resolve()
                    if directory.is_relative_to((library/'steamapps/common').resolve()):games.append((name,directory))
            except OSError:continue
    return games


def game_candidates(proc=Path('/proc'),home=None):
    installations=steam_installations(home);candidates=[];seen=set()
    for entry in proc.iterdir():
        if not entry.name.isdigit():continue
        try:
            args=(entry/'cmdline').read_bytes().decode(errors='replace').split('\0')
            executable=(entry/'exe').resolve()
            cwd=(entry/'cwd').resolve()
        except (OSError,RuntimeError):continue
        # Only argv[0], /proc/exe and Wine .exe arguments, never arbitrary launcher arguments.
        paths=[executable]
        if args and args[0]:paths.append(Path(args[0]) if Path(args[0]).is_absolute() else cwd/args[0])
        for arg in args[1:]:
            if arg.casefold().endswith('.exe') and not arg.startswith('-'):
                paths.append(Path(arg) if Path(arg).is_absolute() else cwd/arg.replace('\\','/'))
        for path in paths:
            name=path.name
            if any(word in name.casefold() for word in ('launcher','crash','unitycrash','battle.net','steamwebhelper')):continue
            title=next((title for title,folder in installations if path.resolve().is_relative_to(folder)),None)
            if not title and path.suffix.casefold()!='.exe':continue
            key=(title,name)
            if key in seen:continue
            seen.add(key);candidates.append({'title':title or '', 'process':name,'path':str(path),'platform':'Steam' if title else 'Wine/Proton'})
    return candidates


def detect_local(root,fallback=None):
    path=Path(root)/'config/games.json'
    document=ConfigStore(root).read('games.json') if path.exists() else {'games':[]}
    result=detect(document,running_processes(),fallback)
    candidates=game_candidates()
    if not result['gameDetected']:
        # A storefront title is only used when it matches an existing category.
        # List order retains the user's category priority.
        for rule in document.get('games',[]):
            match=next((c for c in candidates if c['title'].casefold()==rule.get('category','').casefold()),None)
            if match:
                result={'detectedGame':rule['category'],'detectedProcess':match['process'],'gameDetected':True,'categorySource':'steam'};break
    result['candidates']=candidates
    return result
