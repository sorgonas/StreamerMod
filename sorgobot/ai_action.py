"""Build AI context from event arguments and preceding native user lookups."""
import json
from .ai_variables import message_context

def context(args):
 result=message_context(args)
 for key in ('userId','targetUserName','targetUserProfileImageUrl','targetChannelTitle','targetChannelDescription','targetGame','tagsDelimited','tier','months','cumulativeMonths'):
  if args.get(key) not in (None,''):result[key]=args[key]
 if 'targetChannelDescription' not in result and args.get('targetDescription'):result['targetChannelDescription']=args['targetDescription']
 return json.dumps(result,ensure_ascii=False,default=str)

async def generate(custom,node,args,expand):
 if not node.get('autoContext'):
  return await custom.llm('text_generation',expand(node.get('prompt','')),args,limit=int(expand(node.get('limit',420))),prompt_kind=node.get('promptKind','chat'),provider={90007:'local',90008:'openai'}.get(node.get('type'),node.get('provider','default')))
 kind=node.get('promptKind','chat');options={}
 if kind=='__custom__':options['custom_instructions']=expand(node.get('prompt',''));kind='behavior'
 return await custom.llm('text_generation',context(args),args,limit=2000,prompt_kind=kind,**options)
