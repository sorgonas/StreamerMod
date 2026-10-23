"""Version of this Linux distribution, independent of Original API coverage."""
from importlib.metadata import version,PackageNotFoundError
from pathlib import Path
import tomllib

def runtime_version():
 try:return version('sorgobot-linux')
 except PackageNotFoundError:
  path=Path(__file__).resolve().parents[1]/'pyproject.toml'
  with path.open('rb') as source:return tomllib.load(source)['project']['version']
