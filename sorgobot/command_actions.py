"""Core command operations shared by the engine and chat permission checks."""
from .core import ActionError
from .catalog import ConfigStore


def has_permission(command, args):
    roles = args.get('roles', [])
    if 'Broadcaster' in roles:
        return True
    groups = command.get('permittedGroups', [])
    users = command.get('permittedUsers', [])
    login = str(args.get('userName', args.get('userLogin', ''))).casefold()
    platform=str(args.get('userType',args.get('platform','twitch'))).casefold()
    if platform=='youtube':
        uid=str(args.get('userId',args.get('userName','')))
        allowed={str(u).strip() for u in users}
        named=bool(uid and (('youtube:'+uid) in allowed or ('youtube:id:'+uid) in allowed))
    else:named=login in [str(u).casefold() for u in users] or platform+':'+login in [str(u).casefold() for u in users]
    member = bool(set(groups) & set(roles) or named)
    if command.get('permissionMode', 'allow') == 'deny':
        return bool(groups or users) and not member
    return not (groups or users) or member


def list_commands(commands, node, args):
    aliases = []
    group = node.get('group', 'All')
    for command in commands:
        if group != 'All' and command.get('group', '') != group:
            continue
        if not command.get('enabled', True) or command.get('location', 0) == 2 or command.get('mode', 0) == 1:
            continue
        if not node.get('includeAll', False) and not command.get('include', True):
            continue
        if node.get('onlyHasPermission', False) and not has_permission(command, args):
            continue
        names = [v.strip() for v in command.get('command', '').splitlines() if v.strip()]
        aliases.extend(names[:1] if node.get('ignoreAliases', False) else names)
    name = node.get('resultVariable', 'commands').strip()
    if not name:
        raise ActionError('Variablenname fehlt')
    args[name] = ','.join(aliases)
    args[name + 'List'] = aliases


def command_operation(engine, node, args):
    dispatcher = getattr(engine, 'dispatcher', None)
    if dispatcher is None:
        raise ActionError('Command-Laufzeit ist nicht verfügbar')
    commands = dispatcher.commands
    kind = node['type']
    if kind == 90021:
        list_commands(commands, node, args)
        return
    if kind in (90022, 90025):
        targets = [c for c in commands if c['id'] == node.get('commandId')]
        if not targets:
            raise ActionError('Zielbefehl nicht gefunden')
    else:
        targets = [c for c in commands if c.get('group', '') == node.get('group')]
        if not targets:
            raise ActionError('Befehlsgruppe nicht gefunden oder leer')
    if kind == 90025:
        args['commandState'] = bool(targets[0].get('enabled', True))
        return
    if kind == 90024:
        enabled = {c['id']: c['id'] for c in targets if c.get('enabled', True)}
        disabled = {c['id']: c['id'] for c in targets if not c.get('enabled', True)}
        args.update(commandGroupState=2 if enabled and disabled else 1 if enabled else 0,
                    commandsEnabled=enabled, commandsDisabled=disabled)
        return
    state = node.get('state', 'enabled')
    if state not in ('enabled', 'disabled', 'toggle'):
        raise ActionError('Ungültiger Command-Zustand')
    changes = {c['id']: not c.get('enabled', True) if state == 'toggle' else state == 'enabled' for c in targets}
    if not engine.io.dry_run:
        # Re-read before saving so unrelated editor changes are preserved.
        store = ConfigStore(engine.io.root)
        document = store.read('commands.json')
        for command in document['commands']:
            if command['id'] in changes:
                command['enabled'] = changes[command['id']]
        store.save('commands.json', document)
    for command in targets:
        command['enabled'] = changes[command['id']]
