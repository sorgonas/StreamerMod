"""Points editors use Linux IDs; public reference marks these as v1.1.0."""
USER={'pointDefinitionId':'','user':'%userName%','platform':'%userType%','destinationVariable':'userPoints'}
AMOUNT={**USER,'amount':'0'}
ENTRIES={
90400:('Admin · Get Points Definition',{'pointDefinitionId':'','destinationVariable':'pointsDefinition'}),
90401:('Admin · Reset Points Definition',{'pointDefinitionId':''}),
90402:('Bulk · Award Points to All',{'pointDefinitionId':'','amount':'0','platform':'','onlyActive':False,'activeWindowSeconds':'300','useMultipliers':False}),
90403:('Groups · Award Points to Group',{'pointDefinitionId':'','groupId':'','amount':'0','platform':'','useMultipliers':False}),
90404:('Groups · Get Group Multiplier',{'pointDefinitionId':'','groupId':'','destinationVariable':'groupMultiplier'}),
90405:('Groups · Set Group Multiplier',{'pointDefinitionId':'','groupId':'','multiplier':'1.0'}),
90406:('Groups · Remove Group Multiplier',{'pointDefinitionId':'','groupId':''}),
90407:('Leaderboards · Get Points Leaderboard',{'pointDefinitionId':'','count':'10','offset':'0','platform':'','destinationVariable':'pointsLeaderboard'}),
90408:('User · Award Points',{**AMOUNT,'useMultipliers':False}),
90409:('User · Check Points',{**USER,'requiredAmount':'0','breakOnFailure':True}),
90410:('User · Delete Points',dict(USER)),
90411:('User · Get Points',dict(USER)),
90412:('User · Get User Multiplier',{**USER,'destinationVariable':'userMultiplier'}),
90413:('User · Reset User Points',dict(USER)),
90414:('User · Set Points',dict(AMOUNT)),
90415:('User · Spend Points',{**AMOUNT,'breakOnFailure':True}),
90416:('User · Transfer Points',{'pointDefinitionId':'','sourceUser':'%userName%','sourcePlatform':'%userType%','targetUser':'','targetPlatform':'%userType%','amount':'0','destinationVariable':'userPoints'}),
90417:('User · Update Points',{**AMOUNT,'useMultipliers':False}),
}
