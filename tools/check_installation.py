#!/usr/bin/env python3
"""Read-only installation check: no login, microphone capture or stream start."""
import argparse,importlib,json,shutil,subprocess,sys
from pathlib import Path

def check(without_dotnet=False,without_models=False):
 errors=[];results={}
 for name in ('aiohttp','dbus_next','croniter','dateutil','PySide6.QtWidgets','numpy','scipy','sounddevice','webrtcvad','faster_whisper','vosk','evdev','cv2','grpc','google.protobuf','sorgobot.youtube_proto.stream_list_pb2'):
  try:importlib.import_module(name);results[name]='ok'
  except Exception as exc:results[name]='failed: '+type(exc).__name__;errors.append(name)
 from sorgobot.fresh_project import documents
 from sorgobot.csharp import dotnet_path
 from sorgobot.speech_models import ready
 root=Path(__file__).resolve().parents[1]
 for name in ('ffmpeg','pactl','espeak-ng'):
  results[name]=bool(shutil.which(name))
  if not results[name]:errors.append(name)
 if not without_dotnet:
  try:r=subprocess.run([dotnet_path(),'--list-sdks'],capture_output=True,text=True,timeout=15);ok=r.returncode==0 and any(x.startswith('10.') for x in r.stdout.splitlines())
  except (OSError,subprocess.TimeoutExpired):ok=False
  results['dotnet10']=ok
  if not ok:errors.append('.NET 10 SDK')
 if not without_models:
  results['whisperBase']=ready('de-DE',engine='whisper-base')
  if not results['whisperBase']:errors.append('Whisper Base model')
 # A diagnostic read is allowed, never echo actual config values.
 for name in ('local.json','actions.json','prompts.json'):
  try:json.loads((root/'next-studio/config'/name).read_text());results[name]='valid JSON'
  except (OSError,ValueError):errors.append(name)
 return {'ok':not errors,'checks':results,'missing':errors}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--without-dotnet',action='store_true');parser.add_argument('--without-models',action='store_true');args=parser.parse_args();result=check(args.without_dotnet,args.without_models);print(json.dumps(result,indent=2));sys.exit(0 if result['ok'] else 1)
