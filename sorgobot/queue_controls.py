"""Core Action Queues sub-actions; running actions survive queue clearing."""
from .core import ActionError
from .catalog import ConfigStore
from .action_controls import changed_state


def queue_states(engine):
    return [{'id': None, 'paused': engine.document.get('paused', False),
             'blocking': engine.document.get('blocking', False)},
            *[{'id': q['id'], 'paused': q.get('paused', False),
               'blocking': engine.blocking_queues.get(q['id'], False)}
              for q in engine.document.get('queues', [])]]


def queue_operation(engine, node):
    kind = node['type']
    identity = node.get('queueId')
    states = {s['id']: s for s in queue_states(engine)}
    if identity == 'All':
        if kind == 90052:
            raise ActionError('Blocking benötigt eine einzelne Warteschlange')
        targets = list(states)
    elif identity in states:
        targets = [identity]
    else:
        raise ActionError('Warteschlange nicht gefunden')
    if kind == 90050:
        if identity == 'All':
            targets = list({*targets, *(r['queueId'] for r in engine.pending.values())})
        for target in targets:
            engine.clear_queue(target)
        return
    field = 'paused' if kind == 90051 else 'blocking'
    if kind == 90051:
        state = node.get('state', 'pause')
        if state not in ('pause', 'resume'):
            raise ActionError('Pause State muss Pause oder Resume sein')
        changes = {target: state == 'pause' for target in targets}
    else:
        changes = {target: changed_state(states[target]['blocking'], node.get('state', 'enabled')) for target in targets}
    # Persist only queue fields, without overwriting an edited action definition.
    if not engine.io.dry_run:
        store = ConfigStore(engine.io.root)
        document = store.read('actions.json')
        if None in changes:
            document[field] = changes[None]
        for queue in document.get('queues', []):
            if queue['id'] in changes:
                queue[field] = changes[queue['id']]
        store.save('actions.json', document)
    for target, value in changes.items():
        if field == 'paused':
            engine.queue_pause(target, value)
        else:
            if target is None:
                engine.document['blocking'] = value
            else:
                engine.blocking_queues[target] = value
                next(q for q in engine.document['queues'] if q['id'] == target)['blocking'] = value
        if kind == 90051 and node.get('clear', False):
            engine.clear_queue(target)
