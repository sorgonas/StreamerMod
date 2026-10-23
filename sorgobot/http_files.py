"""Explicit file/directory mappings; never list directories or escape a mapping."""
import mimetypes,uuid
from pathlib import Path,PurePosixPath
from aiohttp import web
from .catalog import ConfigStore
from .core import ActionError
RESERVED={'GetActions','DoAction','GetCredits','ClearCredits','ClearFirstWordsCache','TestCredits','api','credits'}

def validate(rows):
 if not isinstance(rows,list) or len(rows)>100:raise ActionError('Höchstens 100 Dateimappings')
 routes=set()
 for row in rows:
  if not isinstance(row,dict):raise ActionError('Ungültiges Dateimapping')
  route=row.get('route');path=row.get('path')
  if not isinstance(route,str) or not route.startswith('/') or route=='/' or any(c in route for c in '{}?#\\%') or any(p in ('','..','.') for p in route[1:].split('/')) or route.split('/')[1] in RESERVED:raise ActionError('Eindeutigen URL-Pfad wie /overlay angeben')
  if route in routes:raise ActionError('Doppelter URL-Pfad')
  if not isinstance(path,str) or not Path(path).is_absolute():raise ActionError('Absoluten Dateipfad wählen')
  if type(row.get('directory')) is not bool or type(row.get('enabled')) is not bool:raise ActionError('Ungültiges Dateimapping')
  routes.add(route)
 return rows

def mappings(root):
 try:return validate(ConfigStore(root).read('http-files.json'))
 except FileNotFoundError:return []

def install(app,studio):
 async def serve(request):
  parts=PurePosixPath(request.path).parts
  if any(p.startswith('.') or '\\' in p or '\x00' in p for p in parts):raise web.HTTPNotFound()
  for row in sorted(mappings(studio.root),key=lambda r:len(r['route']),reverse=True):
   route=row['route']
   if not row['enabled'] or not (request.path==route or row['directory'] and request.path.startswith(route+'/')):continue
   root=Path(row['path']).resolve()
   target=(root/request.path[len(route):].lstrip('/')).resolve() if row['directory'] else root
   if row['directory'] and not target.is_relative_to(root):raise web.HTTPNotFound()
   if target.is_dir():target=target/'index.html'
   target=target.resolve()
   if row['directory'] and not target.is_relative_to(root):raise web.HTTPNotFound()
   if target.name in ('local.json','.private.json') or target.name.endswith(('.private.json','.sqlite3','.db')) or not target.is_file():raise web.HTTPNotFound()
   return web.FileResponse(target,headers={'X-Content-Type-Options':'nosniff','Cache-Control':'no-cache'})
  raise web.HTTPNotFound()
 app.router.add_get('/{mapped:.*}',serve)
