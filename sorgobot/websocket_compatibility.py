"""Explicit original names without an independent current EventSub producer.

This is a fixed compatibility boundary, not a queue of speculative features.
Sources: Twitch EventSub subscription types and original 1.0.7 enum metadata.
"""
LEGACY_TWITCH_EVENTS={
 'CoinCheer':'No independent current public Twitch EventSub source; the original enum is retained.',
 'CommunityGoalContribution':'Retired Community Goal feature; current channel goals have their own GoalBegin/Progress/End contract.',
 'CommunityGoalEnded':'Retired Community Goal feature; current channel goals have their own GoalBegin/Progress/End contract.',
 'GuestStarSlotUpdate':'Current Twitch guest.update combines guest and slot changes; delivered as GuestStarGuestUpdate, without fabricating a second legacy event.',
 'HypeChat':'No independent current public Twitch EventSub source; ordinary chat is not recast as historical Hype Chat.',
 'HypeChatLevel':'No independent current public Twitch EventSub source; ordinary chat is not recast as historical Hype Chat.'}
