"""Checked original labels/paths, kept separate from executable node defaults."""
import json
from pathlib import Path
REFERENCE=json.loads(Path(__file__).with_suffix('.json').read_text())
def apply_reference(catalog,bucket):
 for raw,entry in REFERENCE[bucket].items():
  kind=int(raw)
  if kind in catalog:catalog[kind]=(entry['path'],catalog[kind][1])
 for kind,(path,defaults) in list(catalog.items()):
  catalog[kind]=(path.replace('Streamer.bot','StreamerMod'),defaults)
 return catalog

FULL_REFERENCE=json.loads(Path(__file__).with_name('menu_full_reference.json').read_text())
