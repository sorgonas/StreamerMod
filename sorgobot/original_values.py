"""Bounded arithmetic and argument indirection used by original action exports."""
import re
import datetime as dt

def format_value(value,fmt,culture=None):
 from .dotnet_values import format_value as dotnet_format
 return dotnet_format(value,fmt,culture)

def arithmetic(text):
 from .dotnet_values import math_value
 return float(math_value(text,culture='',strict=True))

def render(text,args,engine=None,preserve_unknown=False,_depth=0,_inline=True,_formats=True,_now=None,_keep_unknown=False):
 """Scan source once; substituted values are data, never new parser input."""
 from .core import ActionError
 if _depth>32:raise ActionError('Inline-Ausdruck ist zu tief verschachtelt')
 now=_now or dt.datetime.now().astimezone()
 values={str(k).casefold():v for k,v in args.items()}
 defaults={'date':now,'time':now,'longtime':now,'filedatetime':now,'unixtime':int(now.timestamp()),'lf':'\r\n'}
 for key,value in defaults.items():values.setdefault(key,value)
 date_formats={'date':'yyyy/MM/dd','time':'hh:mm','longtime':'hh:mm:ss','filedatetime':'yyyyMMdd.hhmmss'}
 missing=object();output=[];i=0
 def plain(value):
  from decimal import Decimal
  if preserve_unknown and (type(value) in (int,float) or isinstance(value,(Decimal,dt.datetime,dt.date))):return format_value(value,'')
  return '' if value is None else str(value)
 def nested(body,inline=True,formats=True,keep_unknown=None):return render(body,args,engine,preserve_unknown,_depth+1,inline,formats,now,_keep_unknown if keep_unknown is None else keep_unknown)
 while i<len(text):
  marker=text[i]
  if marker in '%~@${' and i+1<len(text) and text[i+1]==marker:
   output.append(marker);i+=2;continue
  if _inline and marker=='$':
   match=re.match(r'\$([A-Za-z][A-Za-z0-9_]*)\(',text[i:])
   if match:
    start=i+match.end();end=start;balance=1
    while end<len(text) and balance:
     if text[end]=='(':balance+=1
     elif text[end]==')':balance-=1
     end+=1
    fmt=None;token_end=end
    if balance==0 and end<len(text) and text[end]==':':
     stop=text.find('$',end+1)
     if stop>=0:fmt=text[end+1:stop];token_end=stop
    if balance==0 and token_end<len(text) and text[token_end]=='$':
     name=match[1].casefold();body=text[start:end-1]
     if name in ('math','parse','length') or preserve_unknown:
      try:
       if name=='parse':
        key=nested(body,False,False);value=values.get(key.casefold(),missing)
        result=('%'+key+'%' if preserve_unknown else '') if value is missing else plain(value)
       elif name=='length':
        count=len(nested(body).encode('utf-16-le',errors='surrogatepass'))//2
        result=format_value(count,fmt) if fmt is not None else str(count)
       elif name=='math':
        from .dotnet_values import math_value
        result=math_value(nested(body,keep_unknown=True),strict=not preserve_unknown,fmt=fmt or 'G')
       else:result=nested(body)
      except (SyntaxError,ValueError,TypeError,ZeroDivisionError,OverflowError) as exc:raise ActionError('Ungültiger Inline-Ausdruck: $'+name) from exc
      output.append(result);i=token_end+1;continue
    elif match[1].casefold() in ('math','parse','length') and not preserve_unknown:raise ActionError('Unvollständiger Inline-Ausdruck')
  if marker in ('%','~','@'):
   end=text.find(marker,i+1)
   if end>i+1:
    token=text[i+1:end];key=token;fmt=None
    if _formats and ':' in token:key,fmt=token.split(':',1)
    value=values.get(key.casefold(),missing) if marker=='%' else (getattr(engine,'session_globals',{}).get(key,missing) if marker=='@' else engine.state.get(key,missing)) if engine is not None else missing
    if value is missing:result=text[i:end+1] if preserve_unknown or _keep_unknown or marker=='@' or marker=='~' and engine is None else ''
    else:
     if fmt is None and marker=='%' and key.casefold() in date_formats:
      if isinstance(value,(dt.datetime,dt.date)) or key.casefold()=='filedatetime' and isinstance(value,str) and 'T' in value:fmt=date_formats[key.casefold()]
     result=format_value(value,fmt) if fmt is not None else plain(value)
    output.append(result);i=end+1;continue
  output.append(marker);i+=1
 return ''.join(output)


def functions(text,args,_depth=0):
 return render(text,args,_depth=_depth)
