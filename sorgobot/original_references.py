"""Map documented framework references to .NET and installed SDK assemblies.

Never load or execute a DLL while importing; unknown dependencies stay unresolved.
"""
import re
from pathlib import Path
FRAMEWORK={'mscorlib.dll','system.dll','system.core.dll','system.net.http.dll','system.runtime.serialization.dll','system.reflection.metadata.dll','system.xml.dll','system.xml.linq.dll','microsoft.csharp.dll','netstandard.dll','system.runtime.dll','system.collections.dll','system.text.json.dll'}

def migrate(references):
 if not isinstance(references,list) or any(not isinstance(r,str) for r in references):raise ValueError('C#-Referenzen müssen eine Textliste sein')
 resolved=[];unresolved=[]
 for value in references:
  normalized=re.sub('/+','/',value.replace('\\','/'));name=normalized.rsplit('/',1)[-1].casefold()
  framework_path=bool(re.fullmatch(r'[A-Za-z]:/Windows/Microsoft\.NET/Framework(?:64)?/v[^/]+/[^/]+',normalized,re.I))
  relative=normalized.casefold() in (name,'./'+name)
  if name in FRAMEWORK and (framework_path or relative):continue
  candidate=None
  if name=='newtonsoft.json.dll' and relative:
   from .csharp import dotnet_path
   sdk=Path(dotnet_path()).resolve().parent/'sdk'
   versions=sorted((p for p in sdk.glob('*/Newtonsoft.Json.dll') if p.is_file()),key=lambda p:tuple(int(n) for n in re.findall(r'\d+',p.parent.name)),reverse=True)
   if versions:candidate=str(versions[0].resolve())
  if candidate is None:
   candidate=value;unresolved.append(value)
  if candidate not in resolved:resolved.append(candidate)
 return resolved,unresolved
