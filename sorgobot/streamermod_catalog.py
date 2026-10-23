"""Native OpenDeck and direct instance actions, independent of the SB website."""
ITEM={'buttonId':'%streamDeckButtonId%','deviceId':''}
STEPS={
97100:('Decks · Deck Notify',{'deviceId':'','title':'StreamerMod','description':'','duration':3000}),
97101:('Decks · Item Set Background',{**ITEM,'color':'#302536','image':'','state':0}),
97102:('Decks · Item Set Icon',{**ITEM,'image':'','iconName':'','color':'white','state':0}),
97103:('Decks · Item Set State',{**ITEM,'state':0}),
97104:('Decks · Item Set Title',{**ITEM,'title':'','state':0}),
97105:('Decks · Item Set Value',{**ITEM,'value':'0','state':0}),
97106:('Decks · Item Toggle State',dict(ITEM)),
97107:('Decks · Page Next',{'deviceId':''}),
97108:('Decks · Page Previous',{'deviceId':''}),
97109:('Decks · Page Set',{'deviceId':'','page':'Default'}),
97200:('Remote · Send Remote Signal',{'instanceId':'','signalName':'','includeArguments':False,'arguments':{}}),
97201:('Remote · Send Remote Trigger',{'instanceId':'','eventName':'','includeArguments':False,'arguments':{}}),
97202:('Remote · Wait For Remote Signal',{'instanceId':'','signalName':'','overwrite':True,'timeout':30000}),
}
TRIGGERS={97250:('Integrations · StreamerMod · Remote Instance Trigger',{'instanceId':'','eventName':''})}
