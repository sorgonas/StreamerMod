#!/usr/bin/env python3
"""Unprivileged StreamerMod deployment, verified SDK/model downloads, desktop setup."""
import argparse,hashlib,json,os,shlex,shutil,subprocess,sys,tarfile,tempfile,urllib.request
from pathlib import Path,PurePosixPath
SOURCE=Path(__file__).resolve().parents[1]

def run(*args,**kw):subprocess.run([str(x) for x in args],check=True,**kw)
def fetch(url,path,expected=None):
 if not url.startswith('https://'):raise ValueError('HTTPS required')
 digest=hashlib.sha512()
 with urllib.request.urlopen(url,timeout=60) as response,Path(path).open('wb') as stream:
  while block:=response.read(1024*1024):stream.write(block);digest.update(block)
 if expected and digest.hexdigest().lower()!=expected.lower():raise ValueError('Download checksum does not match')

def deploy(source,target):
 source=source.resolve();target=target.resolve()
 if target==Path('/') or target==Path.home():raise ValueError('Choose a dedicated application directory')
 target.mkdir(parents=True,exist_ok=True)
 if target.stat().st_uid!=os.getuid():raise ValueError('Installation directory must belong to this user')
 if source==target:return
 ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo')
 for name in ('sorgobot','scripts','tools','docs','.github'):
  if (source/name).is_dir():
   # Tools are allowlisted: no historical development/migration material.
   if name=='tools':
    (target/name).mkdir(exist_ok=True)
    for item in ('build_clean_distribution.py','check_installation.py'):
     if (source/name/item).is_file():shutil.copy2(source/name/item,target/name/item)
   else:shutil.copytree(source/name,target/name,dirs_exist_ok=True,ignore=ignore)
 shutil.copytree(source/'assets/opendeck',target/'assets/opendeck',dirs_exist_ok=True,ignore=ignore)
 for name in ('StreamerMod','start-next-studio.sh','install.sh','install-debian.sh','pyproject.toml','README.md','LICENSE','THIRD-PARTY-NOTICES.md','THIRD-PARTY-SPEECH.md','CONTRIBUTING.md','SECURITY.md','BEREINIGUNG.md','StreamerMod.desktop','.gitignore'):
  if (source/name).is_file():shutil.copy2(source/name,target/name)

def sdk_installed(binary):
 try:r=subprocess.run([str(binary),'--list-sdks'],capture_output=True,text=True,timeout=15);return r.returncode==0 and any(line.startswith('10.') for line in r.stdout.splitlines())
 except (OSError,subprocess.TimeoutExpired):return False

def install_dotnet(target):
 dest=target/'runtimes/dotnet'
 if sdk_installed(dest/'dotnet') or (shutil.which('dotnet') and sdk_installed(shutil.which('dotnet'))):print('.NET 10 SDK already available.',flush=True);return
 arch={'x86_64':'x64','aarch64':'arm64','arm64':'arm64'}.get(os.uname().machine)
 if not arch:raise ValueError('Unsupported .NET architecture')
 url='https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json'
 with urllib.request.urlopen(url,timeout=30) as response:metadata=json.load(response)
 version=metadata['latest-sdk'];entries=[sdk for release in metadata['releases'] for sdk in release.get('sdks',[release.get('sdk',{})]) if sdk.get('version')==version]
 files=[f for sdk in entries for f in sdk.get('files',[]) if f.get('rid')=='linux-'+arch and f.get('name','').endswith('.tar.gz')]
 if not files:raise ValueError('No matching .NET SDK download in Microsoft metadata')
 selected=files[0]
 if not selected['url'].startswith(('https://builds.dotnet.microsoft.com/','https://download.visualstudio.microsoft.com/','https://ci.dot.net/')):raise ValueError('Unexpected SDK download host')
 dest.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='.dotnet-',dir=dest.parent) as tmp:
  tmp=Path(tmp);archive=tmp/'sdk.tar.gz';print('Downloading .NET SDK '+version+' (SHA512 verified).',flush=True);fetch(selected['url'],archive,selected['hash']);unpack=tmp/'unpack';unpack.mkdir()
  with tarfile.open(archive) as tar:
   for member in tar.getmembers():
    p=PurePosixPath(member.name)
    if p.is_absolute() or '..' in p.parts:raise ValueError('Unsafe SDK archive path')
   tar.extractall(unpack,filter='data')
  if not sdk_installed(unpack/'dotnet'):raise ValueError('Downloaded SDK verification failed')
  if dest.exists():
   # Do not discard an existing SDK: overlay the verified, versioned distribution.
   shutil.copytree(unpack,dest,dirs_exist_ok=True)
  else:unpack.rename(dest)
  (dest/'streamermod-sdk-source.json').write_text(json.dumps({'version':version,'source':selected['url'],'sha512':selected['hash']},indent=2))

def desktop_quote(path):return '"'+str(path).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
def shortcuts(target,home=None):
 home=Path(home or Path.home());data=Path(os.environ.get('XDG_DATA_HOME',home/'.local/share'));applications=data/'applications';applications.mkdir(parents=True,exist_ok=True)
 icon=data/'icons/hicolor/256x256/apps/streamermod.png';icon.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target/'sorgobot/resources/StreamerMod.png',icon)
 desktop='[Desktop Entry]\nVersion=1.0\nType=Application\nName=StreamerMod\nComment=Streaming automation for Linux\nExec='+desktop_quote(target/'StreamerMod')+'\nIcon=streamermod\nTerminal=false\nStartupNotify=true\nStartupWMClass=streamermod\nCategories=AudioVideo;\n'
 (applications/'streamermod.desktop').write_text(desktop)
 bindir=home/'.local/bin';bindir.mkdir(parents=True,exist_ok=True);launcher=bindir/'streamermod';launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(target/'StreamerMod'))+' "$@"\n');launcher.chmod(0o755)
 for command,arg in [('update-desktop-database',applications),('gtk-update-icon-cache',data/'icons/hicolor')]:
  if shutil.which(command):subprocess.run([command,'-q',str(arg)],check=False)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--prefix',type=Path,required=True);parser.add_argument('--without-dotnet',action='store_true');parser.add_argument('--without-models',action='store_true');parser.add_argument('--with-opendeck',action='store_true');parser.add_argument('--no-shortcuts',action='store_true');args=parser.parse_args()
 if os.geteuid()==0:raise SystemExit('The application must be installed as the desktop user, never root.')
 target=args.prefix.expanduser().resolve();deploy(SOURCE,target);python=target/'.venv-linux/bin/python'
 if not python.is_file():run(sys.executable,'-m','venv',target/'.venv-linux')
 run(python,'-m','pip','install','--upgrade','pip','setuptools','wheel')
 run(python,'-m','pip','install','-e',str(target)+'[desktop,voice,keyboard,camera,youtube]')
 run(python,'-c',"from pathlib import Path;from sorgobot.next_desktop import initialize;from sorgobot.catalog import ConfigStore;from sorgobot.fresh_project import documents;p=Path('.');initialize(p/'next-studio',p);(p/'config').mkdir(exist_ok=True);store=ConfigStore(p);[(store.save(k,v) if not (p/'config'/k).exists() else None) for k,v in documents().items()];(p/'next-studio/assets').mkdir(exist_ok=True)",cwd=target)
 if not args.without_dotnet:install_dotnet(target)
 if not args.without_models:
  print('Installing verified Whisper Base model (German and English). No microphone is activated.',flush=True)
  run(python,'-c',"import asyncio,aiohttp;from sorgobot.speech_models import install\nasync def main():\n async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800)) as session: await install(session,'de-DE',engine='whisper-base')\nasyncio.run(main())",cwd=target)
 if args.with_opendeck:run(python,'-c',"from pathlib import Path;from sorgobot.streamdeck_support import install_plugin;install_plugin(Path('.'))",cwd=target)
 if not args.no_shortcuts:shortcuts(target)
 run(python,target/'tools/check_installation.py',*(['--without-dotnet'] if args.without_dotnet else []),*(['--without-models'] if args.without_models else []),cwd=target)
 print('\nStreamerMod installed. Start it from the application menu or '+str(target/'StreamerMod')+'.\nNo accounts were added and no stream was started.',flush=True)
if __name__=='__main__':main()
