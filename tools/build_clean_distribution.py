#!/usr/bin/env python3
"""Build from an allowlist and fresh defaults; never copy a working account/state."""
import argparse,shutil,sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sorgobot.fresh_project import documents
from sorgobot.catalog import ConfigStore

def build(source,destination,repository=False):
 source=source.resolve();destination=destination.resolve()
 if destination.exists():raise ValueError('Ziel existiert bereits; nicht überschrieben.')
 destination.mkdir(parents=True)
 ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo','.DS_Store')
 shutil.copytree(source/'sorgobot',destination/'sorgobot',ignore=ignore)
 for name in ('StreamerMod','start-next-studio.sh','install.sh','install-debian.sh','pyproject.toml','README.md','THIRD-PARTY-SPEECH.md','StreamerMod.desktop','.gitignore','BEREINIGUNG.md','LICENSE','THIRD-PARTY-NOTICES.md','CONTRIBUTING.md','SECURITY.md'):
  if (source/name).exists():shutil.copy2(source/name,destination/name)
 shutil.copytree(source/'assets/opendeck',destination/'assets/opendeck',ignore=ignore)
 (destination/'tools').mkdir()
 for name in ('build_clean_distribution.py','check_installation.py'):shutil.copy2(source/'tools'/name,destination/'tools'/name)
 for name in ('docs','.github'):
  if (source/name).is_dir():shutil.copytree(source/name,destination/name,ignore=ignore)
 (destination/'tests').mkdir()
 for name in ('test_installer.py','test_fresh_project.py','test_keyguard.py','test_ai_action_context.py','test_ai_prompt_fields.py'):
  if (source/'tests'/name).is_file():shutil.copy2(source/'tests'/name,destination/'tests'/name)
 (destination/'scripts').mkdir()
 for name in ('install-user.py','install-streamermod-keyguard.sh','streamermod-keyguard.py','install-opendeck-system.sh','setup-streamermod-live-examples.py','setup-streamermod-deck-examples.py'):
  shutil.copy2(source/'scripts'/name,destination/'scripts'/name)
 if not repository:
  for folder in ('config','next-studio/config'):
   (destination/folder).mkdir(parents=True);store=ConfigStore((destination/folder).parent)
   for name,value in documents().items():store.save(name,value)
  (destination/'next-studio/assets').mkdir()
  (destination/'state').mkdir();(destination/'next-studio/state').mkdir()
 files=[str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()]
 return {'files':len(files),'runtimeAccountsIncluded':False,'workingConfigurationCopied':False}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('destination',type=Path);parser.add_argument('--repository',action='store_true');args=parser.parse_args();print(json.dumps(build(Path(__file__).resolve().parents[1],args.destination,args.repository),indent=2))
