"""Execution metadata shared by native sub-actions, C# and action history."""
import copy

FIELDS=frozenset(('actionId','actionName','runningActionId','actionQueuedAt'))
_LOWER=frozenset(name.casefold() for name in FIELDS)

def stamp(arguments,record):
    # An inherited/requeued payload must not identify a previous execution.
    for name in list(arguments):
        if name.casefold() in _LOWER:del arguments[name]
    arguments.update(actionId=record['actionId'],actionName=record['name'],
                     runningActionId=record['id'],actionQueuedAt=record['queuedAt'])

def merge_child(parent,child):
    """Return child outputs while retaining the caller's execution metadata."""
    result=copy.deepcopy(parent)
    result.update({name:value for name,value in child.items() if name.casefold() not in _LOWER})
    return result
