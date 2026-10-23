"""Portable subset of original Win32 virtual-key exports."""
KEYS={**{n:chr(n) for n in range(48,58)},**{n:chr(n) for n in range(65,91)},**{111+n:'F'+str(n) for n in range(1,25)},8:'BACKSPACE',9:'TAB',13:'ENTER',19:'PAUSE',20:'CAPSLOCK',27:'ESC',32:'SPACE',33:'PAGEUP',34:'PAGEDOWN',35:'END',36:'HOME',37:'LEFT',38:'UP',39:'RIGHT',40:'DOWN',45:'INSERT',46:'DELETE',91:'SUPER',92:'SUPER',144:'NUMLOCK',145:'SCROLLLOCK'}
def sequence(key,modifiers):
 if type(key) is not int or key not in KEYS:raise ValueError('Windows-Taste besitzt noch keine portable Linux-Zuordnung: '+str(key))
 if type(modifiers) is not int or modifiers&~7:raise ValueError('Unbekannte Tastatur-Modifizierer')
 return '+'.join([label for bit,label in ((1,'ALT'),(2,'CTRL'),(4,'SHIFT')) if modifiers&bit]+[KEYS[key]])

def original(sequence):
 parts=sequence.upper().split('+');keys={name:key for key,name in KEYS.items()};modifiers=0
 for part in parts[:-1]:
  if part not in ('ALT','CTRL','SHIFT'):raise ValueError('Tastenkombination hat keine Original-Zuordnung')
  modifiers|={'ALT':1,'CTRL':2,'SHIFT':4}[part]
 if parts[-1] not in keys:raise ValueError('Taste hat keine Original-Zuordnung')
 return keys[parts[-1]],modifiers
