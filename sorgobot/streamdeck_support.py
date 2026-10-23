"""Local OpenDeck package and USB readiness; never claims protocol support from VID alone."""
import hashlib
import json
import os
from pathlib import Path
import shutil


def package_info(project):
    folder=Path(project)/'runtimes/opendeck'
    metadata=json.loads((folder/'package.json').read_text())
    package=folder/metadata['file']
    if package.parent!=folder or not package.is_file():raise ValueError('OpenDeck-Paket fehlt')
    if hashlib.sha256(package.read_bytes()).hexdigest()!=metadata['sha256']:
        raise ValueError('OpenDeck-Prüfsumme stimmt nicht')
    return metadata,package


def usb_devices(sysroot=Path('/sys'),devroot=Path('/dev'),access=os.access):
    rows=[]
    for device in sorted((Path(sysroot)/'bus/usb/devices').glob('*')):
        try:
            if (device/'idVendor').read_text().strip().lower()!='0fd9':continue
            product=(device/'idProduct').read_text().strip().lower()
            name=(device/'product').read_text().strip() if (device/'product').exists() else 'Elgato USB device'
            # Other Elgato products (cameras/capture cards etc.) are not decks.
            if 'stream deck' not in name.casefold():continue
            nodes=[]
            for hid in (Path(sysroot)/'class/hidraw').glob('hidraw*'):
                if device.resolve() in (hid/'device').resolve().parents:
                    node=Path(devroot)/hid.name
                    nodes.append({'path':str(node),'accessible':access(node,os.R_OK|os.W_OK)})
            rows.append({'name':name,'usbId':'0fd9:'+product,'location':device.name,
                         'nodes':nodes,'accessible':bool(nodes) and all(n['accessible'] for n in nodes)})
        except OSError:continue
    return rows


def executable():
    return shutil.which('opendeck')


def running():
    """A page command must not start a second lifetime for the external host."""
    for process in Path('/proc').glob('[0-9]*'):
        try:
            if process.stat().st_uid==os.getuid() and (process/'comm').read_text().strip().casefold()=='opendeck':return True
        except OSError:continue
    return False


def install_plugin(project,config_home=None):
    source=Path(project)/'assets/opendeck/org.sorgobot.studio.sdPlugin'
    target=(Path(config_home) if config_home else Path(os.environ.get('XDG_CONFIG_HOME') or Path.home()/'.config'))/'opendeck/plugins'/source.name
    # This namespace belongs to this project. User profiles and other plugins
    # are outside the copy target and are never modified by installation.
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copytree(source,target,dirs_exist_ok=True)
    return target
