"""Action controls change the current engine session, like Set Action State."""
import math
from .core import ActionError, walk


def changed_state(current, state):
    if isinstance(state, bool):
        return state
    if state == 'toggle':
        return not current
    if state in ('enabled', 'disabled'):
        return state == 'enabled'
    raise ActionError('Ungültiger Aktionszustand')


def action_operation(engine, node, args):
    kind = node['type']
    if kind in (90026, 90027):
        actions = [a for a in engine.actions.values() if a.get('group', '') == node.get('group')]
        if not actions:
            raise ActionError('Aktionsgruppe nicht gefunden oder leer')
        if kind == 90026:
            enabled = [a['id'] for a in actions if a.get('enabled', True)]
            disabled = [a['id'] for a in actions if not a.get('enabled', True)]
            args.update(actionGroupState=2 if enabled and disabled else 1 if enabled else 0,
                        actionsEnabled=enabled, actionsDisabled=disabled)
        else:
            states = [changed_state(a.get('enabled', True), node.get('state', 'enabled')) for a in actions]
            for action, state in zip(actions, states):
                action['enabled'] = state
        return
    action = engine.actions.get(node.get('actionId'))
    if action is None:
        raise ActionError('Zielaktion nicht gefunden')
    target = next((n for n in walk(action.get('subActions', [])) if n.get('id') == node.get('subActionId')), None)
    if target is None:
        raise ActionError('Ziel-Unteraktion nicht gefunden')
    if kind == 90028:
        if target['type'] in (99901, 99902):
            raise ActionError('If/Else-Zweige werden durch ihre Bedingung gesteuert')
        target['enabled'] = changed_state(target.get('enabled', True), node.get('state', 'enabled'))
    else:
        try:
            weight = float(node.get('weight', 1))
        except (TypeError, ValueError):
            raise ActionError('Gewichtung muss eine Zahl sein') from None
        if not math.isfinite(weight) or weight < 0:
            raise ActionError('Gewichtung muss endlich und mindestens 0 sein')
        target['weight'] = weight
