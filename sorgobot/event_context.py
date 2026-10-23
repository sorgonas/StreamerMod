"""Translate real/native trigger IDs to verified Original 1.0.7 event metadata."""
from .event_metadata import EVENT_TYPES,TYPE_SOURCES,NATIVE_TYPES,GENERIC_OBS_IDS
_ORIGINAL_VALUES=frozenset(EVENT_TYPES.values())

def arguments(kind,values):
 result=dict(values)
 # Incoming event data cannot spoof reserved event metadata.
 result.pop('__source',None);result.pop('eventSource',None)
 value=NATIVE_TYPES.get(kind,kind if type(kind) is int and kind in _ORIGINAL_VALUES else None)
 source=TYPE_SOURCES.get(value)
 result.update(nativeTriggerType=kind,eventTypeKnown=source is not None,eventTypeMapping='generic' if kind in GENERIC_OBS_IDS else 'exact' if source is not None else 'unknown')
 if source is not None:result.update(__source=value,eventSource=source)
 return result
