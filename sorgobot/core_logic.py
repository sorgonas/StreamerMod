"""Structured loop control stays within the current action and nearest loop."""
import asyncio
import contextvars
import re
from .core import ActionError,expand

class LoopBreak(Exception):pass
class LoopContinue(Exception):pass
DEPTH=contextvars.ContextVar('core_loop_depth',default=0)

def typed(value,auto):
    if not auto or not isinstance(value,str):return value
    if value.casefold() in ('true','false'):return value.casefold()=='true'
    try:return int(value)
    except ValueError:
        try:return float(value)
        except ValueError:return value

def resolve(value,args,engine=None):
    """Keep already typed arguments; resolve persisted globals in logic inputs."""
    if not isinstance(value,str):return value
    match=re.fullmatch(r'%([^%]+)%',value)
    if match:
        key=match[1].casefold()
        for name,item in args.items():
            if str(name).casefold()==key:return item
    match=re.fullmatch(r'~([^~]+)~',value)
    if match and engine is not None:return engine.state.get(match[1],'')
    from .original_values import render
    from .core import PARSE_CONTEXT
    return render(value,args,engine,preserve_unknown=PARSE_CONTEXT.get()[1])

def equal(a,b,auto,ignore):
    a,b=typed(a,auto),typed(b,auto)
    if ignore and isinstance(a,str) and isinstance(b,str):a,b=a.casefold(),b.casefold()
    numeric=lambda v:isinstance(v,(int,float)) and not isinstance(v,bool)
    return (type(a)==type(b) or isinstance(a,str) and isinstance(b,str) or (numeric(a) and numeric(b))) and a==b

def compare(a,b,auto,ignore,less):
    a,b=typed(a,auto),typed(b,auto)
    if ignore and isinstance(a,str) and isinstance(b,str):a,b=a.casefold(),b.casefold()
    numeric=lambda v:isinstance(v,(int,float)) and not isinstance(v,bool)
    if not ((isinstance(a,str) and isinstance(b,str)) or (numeric(a) and numeric(b))):
        raise ActionError('Vergleich benötigt zwei Texte oder zwei Zahlen; Auto Type prüfen')
    return a<b if less else a>b

def matches(node,args,engine=None):
    a,b=resolve(node.get('input',''),args,engine),resolve(node.get('value',''),args,engine);op=node.get('operator','equals')
    if op in ('equals','notEquals'):
        result=equal(a,b,node.get('autoType'),node.get('ignoreCase'));return result if op=='equals' else not result
    if op not in ('lessThan','greaterThan'):raise ActionError('Unbekannter While-Operator')
    return compare(a,b,node.get('autoType'),node.get('ignoreCase'),op=='lessThan')

async def logic(engine,node,args,action):
    kind=node['type']
    if kind in (90162,90163):
        if DEPTH.get()==0:raise ActionError('Loop Break/Continue benötigt eine While-Schleife')
        raise LoopBreak() if kind==90162 else LoopContinue()
    if kind==90161:
        limit=int(node.get('maxIterations',10000))
        if limit<1:raise ActionError('While benötigt mindestens eine erlaubte Iteration')
        token=DEPTH.set(DEPTH.get()+1)
        try:
            count=0
            while matches(node,args,engine):
                count+=1
                if count>limit:raise ActionError('While überschreitet die maximale Iterationszahl')
                try:await engine.nodes(node.get('subActions',[]),args,action)
                except LoopBreak:break
                except LoopContinue:pass
                await asyncio.sleep(0)
        finally:DEPTH.reset(token)
    else:
        default=None;value=resolve(node.get('input',''),args,engine)
        for case in node.get('subActions',[]):
            if not case.get('enabled',True):continue
            if case.get('default'):default=case;continue
            if any(equal(value,resolve(v,args,engine),node.get('autoType'),case.get('_originalCaseIgnoreCase',node.get('ignoreCase'))) for v in case.get('values',[])):
                await engine.nodes(case.get('subActions',[]),args,action);return
        if default:await engine.nodes(default.get('subActions',[]),args,action)
