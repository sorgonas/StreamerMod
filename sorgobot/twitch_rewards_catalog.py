"""Native reward IDs; serialized Original IDs are deliberately not assumed."""
ENTRIES={
 90500:('Get Reward Info',{'rewardId':'%rewardId%'}),
 90501:('Set Enabled State',{'rewardId':'%rewardId%','state':'enabled'}),
 90502:('Set Paused State',{'rewardId':'%rewardId%','state':'paused'}),
 90503:('Set Title',{'rewardId':'%rewardId%','title':'','resetToOriginal':False}),
 90504:('Set Prompt',{'rewardId':'%rewardId%','prompt':'','resetToOriginal':False}),
 90505:('Set Cost',{'rewardId':'%rewardId%','cost':1,'operator':'none'}),
 90506:('Set Background Color',{'rewardId':'%rewardId%','color':'#9147FF','randomColor':False}),
 90507:('Set Max Per Stream',{'rewardId':'%rewardId%','redeems':0,'additive':False}),
 90508:('Set Max per User Per Stream',{'rewardId':'%rewardId%','redeems':0,'additive':False}),
 90509:('Set Global Cooldown',{'rewardId':'%rewardId%','cooldown':0,'additive':False}),
 90510:('Update',{'rewardId':'%rewardId%','title':'','prompt':'','cost':1,'operator':'none','resetToOriginal':False}),
 90511:('Update Redemption Status',{'rewardId':'%rewardId%','redemptionId':'%redemptionId%','status':'FULFILLED'}),
 90512:('Set Group Enabled State',{'group':'','state':'enabled'}),
 90513:('Set Group Paused State',{'group':'','state':'paused'}),
 90514:('Reset Reward Counter',{'rewardId':'%rewardId%'}),
 90515:('Reset Reward User Counters',{'rewardId':'%rewardId%'}),
 90516:('Configure Rewards',{'rewards':[],'disableNotConfigured':False}),
}
TRIGGERS={90550:('Reward Redemption Updated',{'rewardId':'','rewardStatus':''})}
