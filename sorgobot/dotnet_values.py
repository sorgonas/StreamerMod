"""Bounded JSON-only worker for CLR formatting and the pinned mXparser 6.1.0 engine."""
import atexit,functools,datetime as dt,hashlib,json,math,os,select,subprocess,threading,time
from decimal import Decimal
from pathlib import Path

_lock=threading.RLock();_process=None

@functools.lru_cache(maxsize=1)
def paths():
 source=Path(__file__).with_name('value_host').joinpath('Program.cs')
 vendor=source.parent.parent/'vendor/mxparser-6.1.0'
 digest=hashlib.sha256(source.read_bytes())
 for item in [vendor/'MathParser.org-mXparser.dll',vendor/'LICENSE.txt']:digest.update(item.relative_to(vendor).as_posix().encode());digest.update(item.read_bytes())
 cache=source.parents[2]/'state/dotnet-values'/digest.hexdigest()[:24]
 return source,cache,cache/'out/Values.dll'

def prepare():
 from .core import ActionError
 from .csharp import dotnet_path,dotnet_env
 with _lock:
  source,cache,dll=paths()
  if dll.is_file():return dll
  cache.mkdir(parents=True,exist_ok=True)
  (cache/'Program.cs').write_bytes(source.read_bytes())
  from xml.sax.saxutils import escape
  vendor=source.parent.parent/'vendor/mxparser-6.1.0'
  project=cache/'Values.csproj';project.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><ImplicitUsings>enable</ImplicitUsings><Nullable>enable</Nullable></PropertyGroup><ItemGroup><Reference Include="MathParser.org-mXparser"><HintPath>'+escape(str(vendor/'MathParser.org-mXparser.dll'))+'</HintPath><Private>true</Private></Reference><None Include="'+escape(str(vendor/'LICENSE.txt'))+'" Link="mXparser-LICENSE.txt" CopyToOutputDirectory="PreserveNewest" /></ItemGroup></Project>')
  try:result=subprocess.run([dotnet_path(),'build',str(project),'-o',str(cache/'out'),'-v','quiet','--nologo'],env=dotnet_env(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
  except (OSError,subprocess.TimeoutExpired) as exc:raise ActionError('Der .NET-Wertdienst konnte nicht vorbereitet werden.') from exc
  (cache/'build.log').write_bytes(result.stdout)
  if result.returncode or not dll.is_file():raise ActionError('Die Vorbereitung des .NET-Wertdienstes ist fehlgeschlagen; build.log prüfen.')
  return dll

def close():
 global _process
 with _lock:
  if _process is not None:
   process=_process;_process=None
   if process.poll() is None:process.terminate()
   try:process.wait(timeout=1)
   except subprocess.TimeoutExpired:process.kill();process.wait()
   for stream in (process.stdin,process.stdout):
    if stream:stream.close()
atexit.register(close)

def format_value(value,fmt,culture=None):
 from .core import ActionError
 if value is None:return ''
 kind='string'
 if type(value) is bool:kind='bool'
 elif type(value) is int:kind='integer'
 elif type(value) is float:
  if not math.isfinite(value):raise ActionError('Nicht endlicher Zahlenwert kann nicht formatiert werden.')
  kind='float'
 elif isinstance(value,Decimal):kind='decimal'
 elif isinstance(value,(dt.datetime,dt.date)):
  kind='offset' if isinstance(value,dt.datetime) and value.tzinfo is not None else 'date';value=value.isoformat()
 elif isinstance(value,str):
  # Preserve the native parser's established ISO-date convenience.
  try:
   if 'T' in value or len(value)==10:
    parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'));kind='date' if value.endswith('Z') or parsed.tzinfo is None else 'offset'
  except ValueError:pass
 request={'kind':kind,'value':str(value),'format':fmt,'culture':culture}
 if not isinstance(fmt,str) or len(fmt)>512 or len(request['value'])>16000:raise ActionError('Wert oder Format ist zu lang oder ungültig.')
 return request_value(request)

def math_value(text,culture=None,strict=False,fmt='G'):
 from .core import ActionError
 if not isinstance(fmt,str) or len(fmt)>512:raise ActionError('Math-Format ist zu lang oder ungültig.')
 if not isinstance(text,str) or len(text)>1000:raise ActionError('Math-Ausdruck ist zu lang oder ungültig.')
 # Bound parser recursion before entering the third-party engine.
 depth=0
 for char in text:
  if char=='(':depth+=1
  elif char==')':depth-=1
  if depth>128:raise ActionError('Math-Verschachtelung überschreitet 128 Ebenen.')
 return request_value({'kind':'math','value':text,'format':fmt,'culture':culture,'strict':strict})

def request_value(request):
 global _process
 from .core import ActionError
 from .csharp import dotnet_path,dotnet_env
 with _lock:
  dll=prepare()
  if _process is None or _process.poll() is not None:
   close()
   try:_process=subprocess.Popen([dotnet_path(),str(dll)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env={**dotnet_env(),'DOTNET_GCHeapHardLimit':'8000000'},start_new_session=True)
   except OSError as exc:raise ActionError('Der .NET-Wertdienst konnte nicht gestartet werden.') from exc
  try:
   _process.stdin.write((json.dumps(request,ensure_ascii=True)+'\n').encode());_process.stdin.flush()
   deadline=time.monotonic()+5;reply=b''
   while b'\n' not in reply:
    remaining=deadline-time.monotonic()
    if remaining<=0 or not select.select([_process.stdout],[],[],remaining)[0]:raise TimeoutError()
    chunk=os.read(_process.stdout.fileno(),65536)
    if not chunk or len(reply)+len(chunk)>400000:raise OSError('Ungültige Formatantwort')
    reply+=chunk
   result=json.loads(reply)
  except (OSError,ValueError,TimeoutError) as exc:
   close();raise ActionError('Der .NET-Wertdienst antwortet nicht gültig; der nächste Aufruf startet ihn neu.') from exc
 if 'error' in result:raise ActionError(('Ungültiger Math-Ausdruck: ' if request['kind']=='math' else 'Ungültiges .NET-Format: ')+str(result.get('message',result['error']))[:500])
 return result['result']
