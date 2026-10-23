using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using System.IO;
using System.Text.Json.Serialization;
using Streamer.bot.Plugin.Interface.Model;
using Streamer.bot.Plugin.Interface.Enums;
using Streamer.bot.Common.Events;

public class SorgobotCPH
{
    private static readonly System.Text.RegularExpressions.Regex RegexEscapeText=new("(['^$.|?*+()\\\\])",System.Text.RegularExpressions.RegexOptions.Compiled);
    private static readonly JsonSerializerOptions ValueOptions = new() { Converters = { new NativeValueConverter() } };
    private static T Read<T>(JsonElement value)=>value.ValueKind==JsonValueKind.Null ? default! : value.Deserialize<T>(ValueOptions)!;
    public Dictionary<string, object?> args = new();
    private readonly TextWriter protocol;
    private readonly TextReader input;
    private readonly string codeId;
    private int localDepth;
    internal Func<string,bool>? LocalMethod;
    public SorgobotCPH(TextWriter protocol, TextReader input, JsonElement arguments, string codeId="")
    {
        this.protocol=protocol;this.input=input;this.codeId=codeId;
        LoadArguments(arguments);
    }
    internal void LoadArguments(JsonElement arguments)
    {
        foreach(var item in arguments.EnumerateObject()) {
            // Python stores the queue timestamp as ISO text. Restore its documented C# type.
            if(item.Name=="actionQueuedAt" && item.Value.ValueKind==JsonValueKind.String &&
                DateTime.TryParse(item.Value.GetString(),System.Globalization.CultureInfo.InvariantCulture,System.Globalization.DateTimeStyles.RoundtripKind,out var queuedAt))
                args[item.Name]=queuedAt;
            else args[item.Name]=item.Value.Clone();
        }
    }
    private JsonElement Rpc(string method, params object?[] values)
    {
        protocol.WriteLine(JsonSerializer.Serialize(new {type="rpc",method,values}));protocol.Flush();
        using var response=JsonDocument.Parse(input.ReadLine() ?? throw new Exception("Bridge disconnected"));
        if(response.RootElement.TryGetProperty("error",out var error))throw new Exception(error.GetString());
        return response.RootElement.GetProperty("result").Clone();
    }
    private EventType CurrentEventType()
    {
        if(!args.TryGetValue("__source",out var data))return (EventType)0;
        if(data is EventType exact)return exact;
        if(data is JsonElement json && json.ValueKind==JsonValueKind.Number && json.TryGetInt32(out var number))return (EventType)number;
        throw new InvalidOperationException("__source must contain an EventType value");
    }
    public EventType GetEventType()=>CurrentEventType();
    public EventSource GetSource()
    {
        if(!args.ContainsKey("__source"))return EventSource.General;
        return CurrentEventType() switch
        {
            EventType.TwitchFollow => EventSource.Twitch,
            EventType.TwitchCheer => EventSource.Twitch,
            EventType.TwitchSub => EventSource.Twitch,
            EventType.TwitchReSub => EventSource.Twitch,
            EventType.TwitchGiftSub => EventSource.Twitch,
            EventType.TwitchGiftBomb => EventSource.Twitch,
            EventType.TwitchRaid => EventSource.Twitch,
            EventType.TwitchHypeTrainStart => EventSource.Twitch,
            EventType.TwitchHypeTrainUpdate => EventSource.Twitch,
            EventType.TwitchHypeTrainLevelUp => EventSource.Twitch,
            EventType.TwitchHypeTrainEnd => EventSource.Twitch,
            EventType.TwitchRewardRedemption => EventSource.Twitch,
            EventType.TwitchRewardCreated => EventSource.Twitch,
            EventType.TwitchRewardUpdated => EventSource.Twitch,
            EventType.TwitchRewardDeleted => EventSource.Twitch,
            EventType.TwitchAutomaticRewardRedemption => EventSource.Twitch,
            EventType.TwitchPowerUpRedemption => EventSource.Twitch,
            EventType.TwitchCommunityGoalContribution => EventSource.Twitch,
            EventType.TwitchCommunityGoalEnded => EventSource.Twitch,
            EventType.TwitchStreamUpdate => EventSource.Twitch,
            EventType.TwitchWhisper => EventSource.Twitch,
            EventType.TwitchFirstWord => EventSource.Twitch,
            EventType.TwitchSubCounterRollover => EventSource.Twitch,
            EventType.TwitchStreamUpdateGameOnConnect => EventSource.Twitch,
            EventType.TwitchPresentViewers => EventSource.Twitch,
            EventType.TwitchPollCreated => EventSource.Twitch,
            EventType.TwitchPollUpdated => EventSource.Twitch,
            EventType.TwitchPollCompleted => EventSource.Twitch,
            EventType.TwitchPollTerminated => EventSource.Twitch,
            EventType.TwitchPollArchived => EventSource.Twitch,
            EventType.TwitchPredictionCreated => EventSource.Twitch,
            EventType.TwitchPredictionUpdated => EventSource.Twitch,
            EventType.TwitchPredictionCompleted => EventSource.Twitch,
            EventType.TwitchPredictionCanceled => EventSource.Twitch,
            EventType.TwitchPredictionLocked => EventSource.Twitch,
            EventType.TwitchChatMessage => EventSource.Twitch,
            EventType.TwitchChatMessageDeleted => EventSource.Twitch,
            EventType.TwitchUserTimedOut => EventSource.Twitch,
            EventType.TwitchUserBanned => EventSource.Twitch,
            EventType.TwitchUserUnbanned => EventSource.Twitch,
            EventType.TwitchAnnouncement => EventSource.Twitch,
            EventType.TwitchAdRun => EventSource.Twitch,
            EventType.TwitchBotWhisper => EventSource.Twitch,
            EventType.TwitchCharityDonation => EventSource.Twitch,
            EventType.TwitchCharityCompleted => EventSource.Twitch,
            EventType.TwitchCoinCheer => EventSource.Twitch,
            EventType.TwitchShoutoutCreated => EventSource.Twitch,
            EventType.TwitchShoutoutReceived => EventSource.Twitch,
            EventType.TwitchUserUntimedOut => EventSource.Twitch,
            EventType.TwitchCharityStarted => EventSource.Twitch,
            EventType.TwitchCharityProgress => EventSource.Twitch,
            EventType.TwitchGoalBegin => EventSource.Twitch,
            EventType.TwitchGoalProgress => EventSource.Twitch,
            EventType.TwitchGoalEnd => EventSource.Twitch,
            EventType.TwitchShieldModeBegin => EventSource.Twitch,
            EventType.TwitchShieldModeEnd => EventSource.Twitch,
            EventType.TwitchStreamOnline => EventSource.Twitch,
            EventType.TwitchStreamOffline => EventSource.Twitch,
            EventType.TwitchChatCleared => EventSource.Twitch,
            EventType.TwitchRaidStart => EventSource.Twitch,
            EventType.TwitchRaidSend => EventSource.Twitch,
            EventType.TwitchRaidCancelled => EventSource.Twitch,
            EventType.TwitchPyramidSuccess => EventSource.Twitch,
            EventType.TwitchPyramidBroken => EventSource.Twitch,
            EventType.TwitchViewerCountUpdate => EventSource.Twitch,
            EventType.TwitchGuestStarSessionBegin => EventSource.Twitch,
            EventType.TwitchGuestStarSessionEnd => EventSource.Twitch,
            EventType.TwitchGuestStarGuestUpdate => EventSource.Twitch,
            EventType.TwitchGuestStarSlotUpdate => EventSource.Twitch,
            EventType.TwitchGuestStarSettingsUpdate => EventSource.Twitch,
            EventType.TwitchHypeChat => EventSource.Twitch,
            EventType.TwitchHypeChatLevel => EventSource.Twitch,
            EventType.TwitchRewardRedemptionUpdated => EventSource.Twitch,
            EventType.TwitchBroadcasterAuthenticated => EventSource.Twitch,
            EventType.TwitchBroadcasterChatConnected => EventSource.Twitch,
            EventType.TwitchBroadcasterChatDisconnected => EventSource.Twitch,
            EventType.TwitchBroadcasterEventSubConnected => EventSource.Twitch,
            EventType.TwitchBroadcasterEventSubDisconnected => EventSource.Twitch,
            EventType.TwitchBotEventSubConnected => EventSource.Twitch,
            EventType.TwitchBotEventSubDisconnected => EventSource.Twitch,
            EventType.TwitchSevenTVEmoteAdded => EventSource.Twitch,
            EventType.TwitchSevenTVEmoteRemoved => EventSource.Twitch,
            EventType.TwitchBetterTTVEmoteAdded => EventSource.Twitch,
            EventType.TwitchBetterTTVEmoteRemoved => EventSource.Twitch,
            EventType.TwitchUpcomingAd => EventSource.Twitch,
            EventType.TwitchModeratorAdded => EventSource.Twitch,
            EventType.TwitchModeratorRemoved => EventSource.Twitch,
            EventType.TwitchVipAdded => EventSource.Twitch,
            EventType.TwitchVipRemoved => EventSource.Twitch,
            EventType.TwitchUnbanRequestApproved => EventSource.Twitch,
            EventType.TwitchUnbanRequestDenied => EventSource.Twitch,
            EventType.TwitchUnbanRequestCreated => EventSource.Twitch,
            EventType.TwitchBlockedTermsAdded => EventSource.Twitch,
            EventType.TwitchBlockedTermsDeleted => EventSource.Twitch,
            EventType.TwitchPermittedTermsAdded => EventSource.Twitch,
            EventType.TwitchPermittedTermsDeleted => EventSource.Twitch,
            EventType.TwitchChatEmoteModeOn => EventSource.Twitch,
            EventType.TwitchChatEmoteModeOff => EventSource.Twitch,
            EventType.TwitchChatFollowerModeOn => EventSource.Twitch,
            EventType.TwitchChatFollowerModeOff => EventSource.Twitch,
            EventType.TwitchChatFollowerModeChanged => EventSource.Twitch,
            EventType.TwitchChatSlowModeOn => EventSource.Twitch,
            EventType.TwitchChatSlowModeOff => EventSource.Twitch,
            EventType.TwitchChatSlowModeChanged => EventSource.Twitch,
            EventType.TwitchChatSubscriberModeOn => EventSource.Twitch,
            EventType.TwitchChatSubscriberModeOff => EventSource.Twitch,
            EventType.TwitchChatUniqueModeOn => EventSource.Twitch,
            EventType.TwitchChatUniqueModeOff => EventSource.Twitch,
            EventType.TwitchAutoModMessageHeld => EventSource.Twitch,
            EventType.TwitchAutoModMessageUpdate => EventSource.Twitch,
            EventType.TwitchWarnedUser => EventSource.Twitch,
            EventType.TwitchWarningAcknowledged => EventSource.Twitch,
            EventType.TwitchSuspiciousUserMessage => EventSource.Twitch,
            EventType.TwitchSuspiciousUserUpdate => EventSource.Twitch,
            EventType.TwitchWatchStreak => EventSource.Twitch,
            EventType.TwitchModiversary => EventSource.Twitch,
            EventType.TwitchSharedChatSessionBegin => EventSource.Twitch,
            EventType.TwitchSharedChatSessionUpdate => EventSource.Twitch,
            EventType.TwitchSharedChatSessionEnd => EventSource.Twitch,
            EventType.TwitchPrimePaidUpgrade => EventSource.Twitch,
            EventType.TwitchPayItForward => EventSource.Twitch,
            EventType.TwitchGiftPaidUpgrade => EventSource.Twitch,
            EventType.TwitchBitsBadgeTier => EventSource.Twitch,
            EventType.TwitchSharedChatAnnouncement => EventSource.Twitch,
            EventType.TwitchSharedChatRaid => EventSource.Twitch,
            EventType.TwitchSharedChatPrimePaidUpgrade => EventSource.Twitch,
            EventType.TwitchSharedChatGiftPaidUpgrade => EventSource.Twitch,
            EventType.TwitchSharedChatPayItForward => EventSource.Twitch,
            EventType.TwitchSharedChatSub => EventSource.Twitch,
            EventType.TwitchSharedChatResub => EventSource.Twitch,
            EventType.TwitchSharedChatSubGift => EventSource.Twitch,
            EventType.TwitchSharedChatCommunitySubGift => EventSource.Twitch,
            EventType.TwitchSharedChatUserBanned => EventSource.Twitch,
            EventType.TwitchSharedChatUserUnbanned => EventSource.Twitch,
            EventType.TwitchSharedChatUserTimedout => EventSource.Twitch,
            EventType.TwitchSharedChatUserUntimedout => EventSource.Twitch,
            EventType.TwitchSharedChatMessageDeleted => EventSource.Twitch,
            EventType.TwitchSharedModiversary => EventSource.Twitch,
            EventType.TwitchCustomPowerUpRedemption => EventSource.Twitch,
            EventType.StreamlabsDonation => EventSource.Streamlabs,
            EventType.StreamlabsMerchandise => EventSource.Streamlabs,
            EventType.StreamlabsConnected => EventSource.Streamlabs,
            EventType.StreamlabsDisconnected => EventSource.Streamlabs,
            EventType.StreamlabsCharityDonation => EventSource.Streamlabs,
            EventType.StreamlabsAuthenticated => EventSource.Streamlabs,
            EventType.CommandTriggered => EventSource.Command,
            EventType.CommandCooldown => EventSource.Command,
            EventType.SpeechToTextDictation => EventSource.SpeechToText,
            EventType.SpeechToTextCommand => EventSource.SpeechToText,
            EventType.FileWatcherChanged => EventSource.FileWatcher,
            EventType.FileWatcherCreated => EventSource.FileWatcher,
            EventType.FileWatcherDeleted => EventSource.FileWatcher,
            EventType.FileWatcherRenamed => EventSource.FileWatcher,
            EventType.FileTailChanged => EventSource.FileTail,
            EventType.QuoteAdded => EventSource.Quote,
            EventType.QuoteShow => EventSource.Quote,
            EventType.TimedAction => EventSource.Misc,
            EventType.Test => EventSource.Misc,
            EventType.ProcessStarted => EventSource.Misc,
            EventType.ProcessStopped => EventSource.Misc,
            EventType.ChatWindowAction => EventSource.Misc,
            EventType.StreamerbotStarted => EventSource.Misc,
            EventType.StreamerbotExiting => EventSource.Misc,
            EventType.ToastActivation => EventSource.Misc,
            EventType.GlobalVariableUpdated => EventSource.Misc,
            EventType.UserGlobalVariableUpdated => EventSource.Misc,
            EventType.GlobalVariableCreated => EventSource.Misc,
            EventType.GlobalVariableDeleted => EventSource.Misc,
            EventType.RawAction => EventSource.Raw,
            EventType.RawSubAction => EventSource.Raw,
            EventType.RawActionCompleted => EventSource.Raw,
            EventType.WebsocketClientOpen => EventSource.WebsocketClient,
            EventType.WebsocketClientClose => EventSource.WebsocketClient,
            EventType.WebsocketClientMessage => EventSource.WebsocketClient,
            EventType.StreamElementsTip => EventSource.StreamElements,
            EventType.StreamElementsMerch => EventSource.StreamElements,
            EventType.StreamElementsConnected => EventSource.StreamElements,
            EventType.StreamElementsDisconnected => EventSource.StreamElements,
            EventType.StreamElementsAuthenticated => EventSource.StreamElements,
            EventType.WebsocketCustomServerOpen => EventSource.WebsocketCustomServer,
            EventType.WebsocketCustomServerClose => EventSource.WebsocketCustomServer,
            EventType.WebsocketCustomServerMessage => EventSource.WebsocketCustomServer,
            EventType.DonorDriveDonation => EventSource.DonorDrive,
            EventType.DonorDriveProfileUpdated => EventSource.DonorDrive,
            EventType.DonorDriveIncentive => EventSource.DonorDrive,
            EventType.YouTubeBroadcastStarted => EventSource.YouTube,
            EventType.YouTubeBroadcastEnded => EventSource.YouTube,
            EventType.YouTubeMessage => EventSource.YouTube,
            EventType.YouTubeMessageDeleted => EventSource.YouTube,
            EventType.YouTubeUserBanned => EventSource.YouTube,
            EventType.YouTubeSuperChat => EventSource.YouTube,
            EventType.YouTubeSuperSticker => EventSource.YouTube,
            EventType.YouTubeNewSponsor => EventSource.YouTube,
            EventType.YouTubeMemberMileStone => EventSource.YouTube,
            EventType.YouTubeNewSponsorOnlyStarted => EventSource.YouTube,
            EventType.YouTubeNewSponsorOnlyEnded => EventSource.YouTube,
            EventType.YouTubeStatisticsUpdated => EventSource.YouTube,
            EventType.YouTubeBroadcastUpdated => EventSource.YouTube,
            EventType.YouTubeMembershipGift => EventSource.YouTube,
            EventType.YouTubeGiftMembershipReceived => EventSource.YouTube,
            EventType.YouTubeFirstWords => EventSource.YouTube,
            EventType.YouTubePresentViewers => EventSource.YouTube,
            EventType.YouTubeNewSubscriber => EventSource.YouTube,
            EventType.YouTubeBroadcastMonitoringStarted => EventSource.YouTube,
            EventType.YouTubeBroadcastMonitoringEnded => EventSource.YouTube,
            EventType.YouTubeBroadcastAdded => EventSource.YouTube,
            EventType.YouTubeBroadcastRemoved => EventSource.YouTube,
            EventType.YouTubePollClosed => EventSource.YouTube,
            EventType.YouTubePollStarted => EventSource.YouTube,
            EventType.YouTubePollUpdated => EventSource.YouTube,
            EventType.YouTubeJewelsGifted => EventSource.YouTube,
            EventType.YouTubeUserTimedout => EventSource.YouTube,
            EventType.YouTubeSevenTVEmoteAdded => EventSource.YouTube,
            EventType.YouTubeSevenTVEmoteRemoved => EventSource.YouTube,
            EventType.YouTubeBetterTTVEmoteAdded => EventSource.YouTube,
            EventType.YouTubeBetterTTVEmoteRemoved => EventSource.YouTube,
            EventType.PulsoidHeartRatePulse => EventSource.Pulsoid,
            EventType.HypeRateHeartRatePulse => EventSource.HypeRate,
            EventType.HypeRateTwitchClipCreated => EventSource.HypeRate,
            EventType.HypeRateConnected => EventSource.HypeRate,
            EventType.HypeRateDisconnected => EventSource.HypeRate,
            EventType.KofiDonation => EventSource.Kofi,
            EventType.KofiSubscription => EventSource.Kofi,
            EventType.KofiResubscription => EventSource.Kofi,
            EventType.KofiShopOrder => EventSource.Kofi,
            EventType.KofiCommission => EventSource.Kofi,
            EventType.PatreonFollowCreated => EventSource.Patreon,
            EventType.PatreonFollowDeleted => EventSource.Patreon,
            EventType.PatreonPledgeCreated => EventSource.Patreon,
            EventType.PatreonPledgeUpdated => EventSource.Patreon,
            EventType.PatreonPledgeDeleted => EventSource.Patreon,
            EventType.ApplicationActionAdded => EventSource.Application,
            EventType.ApplicationActionUpdated => EventSource.Application,
            EventType.ApplicationActionDeleted => EventSource.Application,
            EventType.ApplicationImport => EventSource.Misc,
            EventType.ApplicationCommandAdded => EventSource.Application,
            EventType.ApplicationCommandUpdated => EventSource.Application,
            EventType.ApplicationCommandDeleted => EventSource.Application,
            EventType.GroupAdded => EventSource.Group,
            EventType.GroupRemoved => EventSource.Group,
            EventType.GroupCleared => EventSource.Group,
            EventType.GroupUsersAdded => EventSource.Group,
            EventType.GroupUsersRemoved => EventSource.Group,
            EventType.TipeeeStreamDonation => EventSource.TipeeeStream,
            EventType.TreatStreamTreat => EventSource.TreatStream,
            EventType.TreatStreamAuthenticated => EventSource.TreatStream,
            EventType.TreatStreamConnected => EventSource.TreatStream,
            EventType.TreatStreamDisconnected => EventSource.TreatStream,
            EventType.ShopifyOrderCreated => EventSource.Shopify,
            EventType.ShopifyOrderPaid => EventSource.Shopify,
            EventType.ObsConnected => EventSource.Obs,
            EventType.ObsDisconnected => EventSource.Obs,
            EventType.ObsEvent => EventSource.Obs,
            EventType.ObsSceneChanged => EventSource.Obs,
            EventType.ObsStreamingStarted => EventSource.Obs,
            EventType.ObsStreamingStopped => EventSource.Obs,
            EventType.ObsRecordingStarted => EventSource.Obs,
            EventType.ObsRecordingStopped => EventSource.Obs,
            EventType.ObsVendorEvent => EventSource.Obs,
            EventType.MidiMessage => EventSource.Midi,
            EventType.InputKeyPress => EventSource.Inputs,
            EventType.InputMouseClick => EventSource.Inputs,
            EventType.StreamDeckAction => EventSource.StreamDeck,
            EventType.StreamDeckConnected => EventSource.StreamDeck,
            EventType.StreamDeckDisconnected => EventSource.StreamDeck,
            EventType.StreamDeckInfo => EventSource.StreamDeck,
            EventType.CustomEvent => EventSource.Custom,
            EventType.CustomCodeEvent => EventSource.Custom,
            EventType.VTubeStudioModelLoaded => EventSource.VTubeStudio,
            EventType.VTubeStudioModelUnloaded => EventSource.VTubeStudio,
            EventType.VTubeStudioBackgroundChanged => EventSource.VTubeStudio,
            EventType.VTubeStudioModelConfigChanged => EventSource.VTubeStudio,
            EventType.VTubeStudioHotkeyTriggered => EventSource.VTubeStudio,
            EventType.VTubeStudioModelAnimation => EventSource.VTubeStudio,
            EventType.VTubeStudioConnected => EventSource.VTubeStudio,
            EventType.VTubeStudioDisconnected => EventSource.VTubeStudio,
            EventType.VTubeStudioTrackingStatusChanged => EventSource.VTubeStudio,
            EventType.VTubeStudioItemEvent => EventSource.VTubeStudio,
            EventType.VTubeStudioModelClicked => EventSource.VTubeStudio,
            EventType.CrowdControlGameSessionStart => EventSource.CrowdControl,
            EventType.CrowdControlGameSessionEnd => EventSource.CrowdControl,
            EventType.CrowdControlEffectRequest => EventSource.CrowdControl,
            EventType.CrowdControlEffectSuccess => EventSource.CrowdControl,
            EventType.CrowdControlEffectFailure => EventSource.CrowdControl,
            EventType.CrowdControlTimedEffectStarted => EventSource.CrowdControl,
            EventType.CrowdControlTimedEffectEnded => EventSource.CrowdControl,
            EventType.CrowdControlTimedEffectUpdated => EventSource.CrowdControl,
            EventType.CrowdControlCoinExchange => EventSource.CrowdControl,
            EventType.ElgatoWaveLinkOutputSwitched => EventSource.Elgato,
            EventType.ElgatoWaveLinkOutputVolumeChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkOutputMuteChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkSelectedOutputChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkInputVolumeChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkInputMuteChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkInputNameChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkMicrophoneGainChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkMicrophoneOutputVolumeChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkMicrophoneBalanceChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkMicrophoneMuteChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkMicrophoneSettingChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkFilterAdded => EventSource.Elgato,
            EventType.ElgatoWaveLinkFilterChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkFilterDeleted => EventSource.Elgato,
            EventType.ElgatoWaveLinkFilterBypassStateChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkConnected => EventSource.Elgato,
            EventType.ElgatoWaveLinkDisconnected => EventSource.Elgato,
            EventType.ElgatoWaveLinkInputLevelMeterChanged => EventSource.Elgato,
            EventType.ElgatoWaveLinkOutputLevelMeterChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubConnected => EventSource.Elgato,
            EventType.ElgatoCameraHubDisconnected => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamConnected => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamrDisconnected => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamActivated => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamDeactivated => EventSource.Elgato,
            EventType.ElgatoCameraHubSelectedWebcamChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamMirrored => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamFlipped => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamDeviceOrientationChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamExposureAutoLockEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamExposureAutoLockDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamSnapshotTaken => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamZoomChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamContrastChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamWhiteBalanceChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamAutoExposureEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamAutoExposureDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamAutoWhiteBalanceEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamAutoWhiteBalanceDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamNoiseReductionEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamNoiseReductionDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamISOChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamShutterSpeedChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamSharpnessChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamAntiFlickerChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamLensChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamARLensChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamBitrateChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamFlashEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamFlashDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamPanChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubTiltChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamOverscanChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamAutoFocusEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamAutoFocusDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamFocusChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamWhiteBalanceTintChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamBrightnessChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamSaturationChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamLiveISOChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamLiveShutterSpeedChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamLiveWhiteBalanceChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubWebcamLiveWhiteBalanceTintChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterConnected => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterDisconnected => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterModeChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterBrightnessChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterFontChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterFontSizeChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterAutoScrollEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterAutoScrollDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterAutoScrollChapterEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterAutoScrollChapterDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterScrollSpeedChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterOpacityChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterHorizontalMarginChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterVerticalMarginChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterLineSpacingChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterFontColorChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterBackgroundColorChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterSelectedChapterChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterChannelsChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterSelectedChannelChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterContrastChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterCrosshairEnabled => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterCrosshairDisabled => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterCrosshairImageChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterCrosshairColorChanged => EventSource.Elgato,
            EventType.ElgatoCameraHubPrompterSelectedScriptChanged => EventSource.Elgato,
            EventType.ElgatoStreamDeckMcpConnected => EventSource.Elgato,
            EventType.ElgatoStreamDeckMcpDisconnected => EventSource.Elgato,
            EventType.StreamlabsDesktopConnected => EventSource.StreamlabsDesktop,
            EventType.StreamlabsDesktopDisconnected => EventSource.StreamlabsDesktop,
            EventType.StreamlabsDesktopSceneChanged => EventSource.StreamlabsDesktop,
            EventType.StreamlabsDesktopStreamingStarted => EventSource.StreamlabsDesktop,
            EventType.StreamlabsDesktopStreamingStopped => EventSource.StreamlabsDesktop,
            EventType.StreamlabsDesktopRecordingStarted => EventSource.StreamlabsDesktop,
            EventType.StreamlabsDesktopRecordingStopped => EventSource.StreamlabsDesktop,
            EventType.SpeakerBotConnected => EventSource.SpeakerBot,
            EventType.SpeakerBotDisconnected => EventSource.SpeakerBot,
            EventType.FourthwallProductCreated => EventSource.Fourthwall,
            EventType.FourthwallProductUpdated => EventSource.Fourthwall,
            EventType.FourthwallGiftPurchase => EventSource.Fourthwall,
            EventType.FourthwallOrderPlaced => EventSource.Fourthwall,
            EventType.FourthwallOrderUpdated => EventSource.Fourthwall,
            EventType.FourthwallDonation => EventSource.Fourthwall,
            EventType.FourthwallSubscriptionPurchased => EventSource.Fourthwall,
            EventType.FourthwallSubscriptionExpired => EventSource.Fourthwall,
            EventType.FourthwallSubscriptionChanged => EventSource.Fourthwall,
            EventType.FourthwallThankYouSent => EventSource.Fourthwall,
            EventType.FourthwallNewsletterSubscribed => EventSource.Fourthwall,
            EventType.FourthwallGiftDrawStarted => EventSource.Fourthwall,
            EventType.FourthwallGiftDrawEnded => EventSource.Fourthwall,
            EventType.ThrowingSystemConnected => EventSource.ThrowingSystem,
            EventType.ThrowingSystemWebsocketConnected => EventSource.ThrowingSystem,
            EventType.ThrowingSystemWebsocketDisconnected => EventSource.ThrowingSystem,
            EventType.ThrowingSystemEventsConnected => EventSource.ThrowingSystem,
            EventType.ThrowingSystemEventsDisconnected => EventSource.ThrowingSystem,
            EventType.ThrowingSystemItemHit => EventSource.ThrowingSystem,
            EventType.ThrowingSystemTriggerActivated => EventSource.ThrowingSystem,
            EventType.ThrowingSystemTriggerEnded => EventSource.ThrowingSystem,
            EventType.PallyggConnected => EventSource.Pallygg,
            EventType.PallyggDisconnected => EventSource.Pallygg,
            EventType.PallyggCampaignTip => EventSource.Pallygg,
            EventType.StreamerBotRemoteInstanceConnected => EventSource.StreamerBotRemote,
            EventType.StreamerBotRemoteInstanceDisconnected => EventSource.StreamerBotRemote,
            EventType.StreamerBotRemoteInstanceTrigger => EventSource.StreamerBotRemote,
            EventType.StreamerBotRemoteInstanceSignal => EventSource.StreamerBotRemote,
            EventType.StreamerBotCustomWebook => EventSource.StreamerBot,
            EventType.VoiceModConnected => EventSource.VoiceMod,
            EventType.VoiceModDisconnected => EventSource.VoiceMod,
            EventType.VoiceModVoiceLoaded => EventSource.VoiceMod,
            EventType.VoiceModSoundboardChanged => EventSource.VoiceMod,
            EventType.MeldStudioConnected => EventSource.MeldStudio,
            EventType.MeldStudioDisconnected => EventSource.MeldStudio,
            EventType.MeldStudioStreamingStarted => EventSource.MeldStudio,
            EventType.MeldStudioStreamingStopped => EventSource.MeldStudio,
            EventType.MeldStudioRecordingStarted => EventSource.MeldStudio,
            EventType.MeldStudioRecordingStopped => EventSource.MeldStudio,
            EventType.MeldStudioSceneChanged => EventSource.MeldStudio,
            EventType.MeldStudioLayerVisbilityChanged => EventSource.MeldStudio,
            EventType.MeldStudioLEffectEnabledStateChanged => EventSource.MeldStudio,
            EventType.MeldStudioTrackMonitoringStateChanged => EventSource.MeldStudio,
            EventType.MeldStudioTrackMustedStateChanged => EventSource.MeldStudio,
            EventType.MeldStudioEvent => EventSource.MeldStudio,
            EventType.KickBroadcasterAuthenticated => EventSource.Kick,
            EventType.KickBroadcasterChatConnected => EventSource.Kick,
            EventType.KickBroadcasterChatDisconnected => EventSource.Kick,
            EventType.KickFirstWords => EventSource.Kick,
            EventType.KickPresentViewers => EventSource.Kick,
            EventType.KickChatMessage => EventSource.Kick,
            EventType.KickFollow => EventSource.Kick,
            EventType.KickStreamOnline => EventSource.Kick,
            EventType.KickStreamOffline => EventSource.Kick,
            EventType.KickSubscription => EventSource.Kick,
            EventType.KickResubscription => EventSource.Kick,
            EventType.KickGiftSubscription => EventSource.Kick,
            EventType.KickMassGiftSubscription => EventSource.Kick,
            EventType.KickUserTimedOut => EventSource.Kick,
            EventType.KickUserBanned => EventSource.Kick,
            EventType.KickChannelUpdate => EventSource.Kick,
            EventType.KickSevenTVEmoteAdded => EventSource.Kick,
            EventType.KickSevenTVEmoteRemoved => EventSource.Kick,
            EventType.KickViewerCountUpdate => EventSource.Kick,
            EventType.KickRewardRedemption => EventSource.Kick,
            EventType.KickKicksGifted => EventSource.Kick,
            EventType.StreamLootsPackPurchased => EventSource.StreamLoots,
            EventType.StreamLootsPackGifted => EventSource.StreamLoots,
            EventType.StreamLootsCardRedeemed => EventSource.StreamLoots,
            EventType.StreamLootsReaction => EventSource.StreamLoots,
            EventType.ThroneGiftPurchased => EventSource.Throne,
            EventType.ThroneContributionPurchased => EventSource.Throne,
            EventType.ThroneGiftCrowdfunded => EventSource.Throne,
            EventType.SystemClipboardChanged => EventSource.System,
            _ => throw new InvalidOperationException("No verified EventSource for this EventType")
        };
    }
    public bool TryGetArg(string argName,out object value)=>TryGetArg<object>(argName,out value);
    public bool TryGetArg<T>(string argName, out T value)
    {
        value=default!;
        if(!args.TryGetValue(argName,out var data))return false;
        try {
            if(data is T exact && (data is not JsonElement || typeof(T)==typeof(JsonElement))){value=exact;return true;}
            var json=data is JsonElement e ? e.GetRawText() : JsonSerializer.Serialize(data);
            value=JsonSerializer.Deserialize<T>(json,ValueOptions)!;return true;
        }catch{return false;}
    }
    public void SetArgument(string variableName,object? value)=>args[variableName]=value;
    public T GetGlobalVar<T>(string varName,bool persisted=true)
    {
        var result=Rpc("global_get",varName,persisted);
        return Read<T>(result);
    }
    public void SetGlobalVar(string varName,object? value,bool persisted=true)=>Rpc("global_set",varName,value,persisted);
    public void UnsetGlobalVar(string varName,bool persisted=true)=>Rpc("global_unset",varName,persisted);
    public void SendMessage(string message,bool useBot=true,bool fallback=true)=>TwitchCall("SendMessage",message,useBot,fallback);
    public void SendAction(string action,bool useBot=true,bool fallback=true)=>TwitchCall("SendAction",action,useBot,fallback);
    public void TwitchSendAndPinMessage(string message)=>TwitchCall("TwitchSendAndPinMessage",message);
    public void LogInfo(string logLine)=>Rpc("log","info",logLine);
    public void LogDebug(string logLine)=>Rpc("log","debug",logLine);
    public void LogWarn(string logLine)=>Rpc("log","warn",logLine);
    public void LogError(string logLine)=>Rpc("log","error",logLine);
    public string Parse(string text,Dictionary<string,object?>? args=null)
    {
        Dictionary<string,object?>? persistedGlobals=null,temporaryGlobals=null;
        string MathText(string expression,string? format) {
            if(expression.Length>1000)throw new FormatException("CPH.Parse math exceeds 1000 characters");
            int depth=0;foreach(char ch in expression) {if(ch=='(')depth++;else if(ch==')')depth--;if(depth>128)throw new FormatException("CPH.Parse math nesting exceeds 128 levels");}
            return Rpc("parse_math",expression,System.Globalization.CultureInfo.CurrentCulture.Name,format).GetString() ?? "";
        }
        return new CphTextParser(args ?? this.args,persisted=> {
            var source=persisted?persistedGlobals:temporaryGlobals;
            if(source==null) {
                source=new Dictionary<string,object?>();
                foreach(var item in GetGlobalVarValues(persisted))source[item.VariableName]=item.Value;
                if(persisted)persistedGlobals=source;else temporaryGlobals=source;
            }
            return source;
        }, MathText).Render(text);
    }
    public int BroadcastUdp(int port,object data)
    {
        // Original 1.0.7 uses object.ToString(), not JSON or raw byte arrays.
        if(port<0 || port>65535)throw new ArgumentOutOfRangeException(nameof(port));
        var payload=System.Text.Encoding.UTF8.GetBytes(data.ToString()!);
        return Rpc("broadcast_udp",port,payload).GetInt32();
    }
    public List<UserVariableValue<T>> GetYouTubeUsersVar<T>(string varName,bool persisted=true)=>Read<List<UserVariableValue<T>>>(Rpc("platform_vars_list","youtube",varName,persisted));
    public T GetYouTubeUserVar<T>(string userName,string varName,bool persisted=true)=>Read<T>(Rpc("platform_var","youtube","get",userName,false,varName,null,persisted));
    public void SetYouTubeUserVar(string userName,string varName,object? value,bool persisted=true)=>Rpc("platform_var","youtube","set",userName,false,varName,value,persisted);
    public void UnsetYouTubeUserVar(string userName,string varName,bool persisted=true)=>Rpc("platform_var","youtube","unset",userName,false,varName,null,persisted);
    public void UnsetYouTubeUser(string userName,bool persisted=true)=>Rpc("platform_var","youtube","unset_user",userName,false,null,null,persisted);
    public T GetYouTubeUserVarById<T>(string userId,string varName,bool persisted=true)=>Read<T>(Rpc("platform_var","youtube","get",userId,true,varName,null,persisted));
    public void SetYouTubeUserVarById(string userId,string varName,object? value,bool persisted=true)=>Rpc("platform_var","youtube","set",userId,true,varName,value,persisted);
    public void UnsetYouTubeUserVarById(string userId,string varName,bool persisted=true)=>Rpc("platform_var","youtube","unset",userId,true,varName,null,persisted);
    public void UnsetYouTubeUserById(string userId,bool persisted=true)=>Rpc("platform_var","youtube","unset_user",userId,true,null,null,persisted);
    public void SetYouTubeUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","youtube","set",userIds,varName,value,persisted);
    public void IncrementYouTubeUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","youtube","increment",userIds,varName,value,persisted);
    public void IncrementOrCreateYouTubeUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","youtube","increment_create",userIds,varName,value,persisted);
    public void IncrementAllYouTubeUsersVar(string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","youtube","all_increment",null,varName,value,persisted);
    public List<UserVariableValue<T>> GetKickUsersVar<T>(string varName,bool persisted=true)=>Read<List<UserVariableValue<T>>>(Rpc("platform_vars_list","kick",varName,persisted));
    public T GetKickUserVar<T>(string userName,string varName,bool persisted=true)=>Read<T>(Rpc("platform_var","kick","get",userName,false,varName,null,persisted));
    public void SetKickUserVar(string userName,string varName,object? value,bool persisted=true)=>Rpc("platform_var","kick","set",userName,false,varName,value,persisted);
    public void UnsetKickUserVar(string userName,string varName,bool persisted=true)=>Rpc("platform_var","kick","unset",userName,false,varName,null,persisted);
    public void UnsetKickUser(string userName,bool persisted=true)=>Rpc("platform_var","kick","unset_user",userName,false,null,null,persisted);
    public T GetKickUserVarById<T>(string userId,string varName,bool persisted=true)=>Read<T>(Rpc("platform_var","kick","get",userId,true,varName,null,persisted));
    public void SetKickUserVarById(string userId,string varName,object? value,bool persisted=true)=>Rpc("platform_var","kick","set",userId,true,varName,value,persisted);
    public void UnsetKickUserVarById(string userId,string varName,bool persisted=true)=>Rpc("platform_var","kick","unset",userId,true,varName,null,persisted);
    public void UnsetKickUserById(string userId,bool persisted=true)=>Rpc("platform_var","kick","unset_user",userId,true,null,null,persisted);
    public void SetKickUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","kick","set",userIds,varName,value,persisted);
    public void IncrementKickUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","kick","increment",userIds,varName,value,persisted);
    public void IncrementOrCreateKickUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","kick","increment_create",userIds,varName,value,persisted);
    public void IncrementAllKickUsersVar(string varName,object value,bool persisted=true)=>Rpc("platform_vars_bulk","kick","all_increment",null,varName,value,persisted);
    public string TwitchClientId=>Read<string>(Rpc("auth_property","twitch_client_id"));
    public string TwitchOAuthToken=>Read<string>(Rpc("auth_property","twitch_token"));
    private string? CurrentUserPlatform()
    {
        args.TryGetValue("eventSource",out var source);var name=source?.ToString();
        if(string.Equals(name,"command",StringComparison.OrdinalIgnoreCase)){args.TryGetValue("commandSource",out source);name=source?.ToString();}
        return name;
    }
    public void UnsetUserVar(string userName,string varName,bool persisted=true)=>Rpc("legacy_user_unset",CurrentUserPlatform(),userName,varName,persisted,false);
    public void UnsetUser(string userName,bool persisted=true)=>Rpc("legacy_user_unset",CurrentUserPlatform(),userName,null,persisted,true);
    public void ResetFirstWords()=>Rpc("reset_first_words");
    [Obsolete("Original 1.0.7 legacy no-op; use platform-specific user variables")]
    public T GetUserVar<T>(string userName,string varName,bool persisted=true)=>default!;
    [Obsolete("Original 1.0.7 legacy no-op; use platform-specific user variables")]
    public void SetUserVar(string userName,string varName,object? value,bool persisted=true){}
    public void KeyboardPress(string keyPress)=>Rpc("keyboard_press",keyPress);
    public void ShowToastNotification(string title,string message,string? attribution=null,string? iconPath=null)=>Rpc("toast",null,title,message,attribution,iconPath);
    public void ShowToastNotification(string id,string title,string message,string? attribution=null,string? iconPath=null)=>Rpc("toast",id,title,message,attribution,iconPath);
    public void TriggerEvent(string eventName,bool useArgs=true)=>Rpc("custom_event",eventName,useArgs ? args : new Dictionary<string,object?>());
    public bool RegisterCustomTrigger(string triggerName,string eventName,string[] categories)=>Rpc("code_register",codeId,triggerName,eventName,categories).GetBoolean();
    public void TriggerCodeEvent(string eventName,bool useArgs=true)=>Rpc("code_event",eventName,useArgs ? args : new Dictionary<string,object?>());
    public void TriggerCodeEvent(string eventName,Dictionary<string,object> args)=>Rpc("code_event",eventName,args);
    public void TriggerCodeEvent(string eventName,string json)
    {
        using var document=JsonDocument.Parse(json);
        if(document.RootElement.ValueKind!=JsonValueKind.Object)throw new ArgumentException("Code event requires a JSON object");
        Rpc("code_event",eventName,document.RootElement.Clone());
    }
    public void AddToCredits(string section,string value,bool json=true)
    {
        object payload=value;
        if(json){using var document=JsonDocument.Parse(value);if(document.RootElement.ValueKind!=JsonValueKind.Object)throw new ArgumentException("Credits JSON requires an object");payload=document.RootElement.Clone();}
        Rpc("credits","add",section.ToLowerInvariant(),payload);
    }
    public void ResetCredits()=>Rpc("credits","reset");
    private JsonElement TwitchCall(string operation,params object?[] values)=>Rpc("twitch_csharp",operation,values);
    public void TwitchReplyToMessage(string message,string replyId,bool useBot=true,bool fallback=true)=>TwitchCall("TwitchReplyToMessage" ,message,replyId,useBot,fallback);
    public bool TwitchClearChannelTags()=>TwitchCall("TwitchClearChannelTags").GetBoolean();
    public bool TwitchSetChannelTags(List<string> tags)=>TwitchCall("TwitchSetChannelTags" ,tags).GetBoolean();
    public bool TwitchAddChannelTag(string tag)=>TwitchCall("TwitchAddChannelTag" ,tag).GetBoolean();
    public bool TwitchRemoveChannelTag(string tag)=>TwitchCall("TwitchRemoveChannelTag" ,tag).GetBoolean();
    public bool TwitchWarnUser(string userName,string reason)=>TwitchCall("TwitchWarnUser" ,userName,reason).GetBoolean();
    public bool TwitchAddActiveMonitoringSuspiciousStatus(string userName)=>TwitchCall("TwitchAddActiveMonitoringSuspiciousStatus" ,userName).GetBoolean();
    public bool TwitchAddRestrictedSuspiciousStatus(string userName)=>TwitchCall("TwitchAddRestrictedSuspiciousStatus" ,userName).GetBoolean();
    public bool TwitchRemoveSuspiciousStatus(string userName)=>TwitchCall("TwitchRemoveSuspiciousStatus" ,userName).GetBoolean();
    public void DisableReward(string rewardId)=>TwitchCall("DisableReward" ,rewardId);
    public void EnableReward(string rewardId)=>TwitchCall("EnableReward" ,rewardId);
    public void PauseReward(string rewardId)=>TwitchCall("PauseReward" ,rewardId);
    public void UnPauseReward(string rewardId)=>TwitchCall("UnPauseReward" ,rewardId);
    public void UpdateRewardCost(string rewardId,int cost,bool additive=false)=>TwitchCall("UpdateRewardCost" ,rewardId,cost,additive);
    public void UpdateRewardCooldown(string rewardId,long cooldown,bool additive=false)=>TwitchCall("UpdateRewardCooldown" ,rewardId,cooldown,additive);
    public void UpdateRewardMaxPerStream(string rewardId,long redeems,bool additive=false)=>TwitchCall("UpdateRewardMaxPerStream" ,rewardId,redeems,additive);
    public void UpdateRewardMaxPerUserPerStream(string rewardId,long redeems,bool additive=false)=>TwitchCall("UpdateRewardMaxPerUserPerStream" ,rewardId,redeems,additive);
    public bool UpdateRewardTitle(string rewardId,string title)=>TwitchCall("UpdateRewardTitle" ,rewardId,title).GetBoolean();
    public bool UpdateRewardPrompt(string rewardId,string prompt)=>TwitchCall("UpdateRewardPrompt" ,rewardId,prompt).GetBoolean();
    public bool UpdateRewardBackgroundColor(string rewardId,string backgroundColor)=>TwitchCall("UpdateRewardBackgroundColor" ,rewardId,backgroundColor).GetBoolean();
    public bool UpdateReward(string rewardId,string title=null,string prompt=null,int? cost=null,string backroundColor=null)=>TwitchCall("UpdateReward" ,rewardId,title,prompt,cost,backroundColor).GetBoolean();
    public bool TwitchRedemptionFulfill(string rewardId,string redemptionId)=>TwitchCall("TwitchRedemptionFulfill" ,rewardId,redemptionId).GetBoolean();
    public bool TwitchRedemptionCancel(string rewardId,string redemptionId)=>TwitchCall("TwitchRedemptionCancel" ,rewardId,redemptionId).GetBoolean();
    public void TwitchRewardGroupEnable(string groupName)=>TwitchCall("TwitchRewardGroupEnable" ,groupName);
    public void TwitchRewardGroupDisable(string groupName)=>TwitchCall("TwitchRewardGroupDisable" ,groupName);
    public void TwitchRewardGroupToggleEnable(string groupName)=>TwitchCall("TwitchRewardGroupToggleEnable" ,groupName);
    public void TwitchRewardGroupPause(string groupName)=>TwitchCall("TwitchRewardGroupPause" ,groupName);
    public void TwitchRewardGroupUnPause(string groupName)=>TwitchCall("TwitchRewardGroupUnPause" ,groupName);
    public void TwitchRewardGroupTogglePause(string groupName)=>TwitchCall("TwitchRewardGroupTogglePause" ,groupName);
    public bool TwitchPollCreate(string title,List<string> choices,int duration,int channelPointsPerVote=0)=>TwitchCall("TwitchPollCreate" ,title,choices,duration,channelPointsPerVote).GetBoolean();
    public void TwitchPollTerminate(string pollId)=>TwitchCall("TwitchPollTerminate" ,pollId);
    public void TwitchPollArchive(string pollId)=>TwitchCall("TwitchPollArchive" ,pollId);
    public void TwitchSubscriberOnly(bool enabled=true)=>TwitchCall("TwitchSubscriberOnly" ,enabled);
    public void TwitchEmoteOnly(bool enabled=true)=>TwitchCall("TwitchEmoteOnly" ,enabled);
    public void TwitchSlowMode(bool enabled=true,int duration=0)=>TwitchCall("TwitchSlowMode" ,enabled,duration);
    public void TwitchFollowMode(bool enabled=true,int duration=0)=>TwitchCall("TwitchFollowMode" ,enabled,duration);
    public string TwitchPredictionCreate(string title,string firstOption,string secondOption,int duration)=>Read<string>(TwitchCall("TwitchPredictionCreate" ,title,new List<string>{firstOption,secondOption},duration));
    public string TwitchPredictionCreate(string title,List<string> options,int duration)=>Read<string>(TwitchCall("TwitchPredictionCreate" ,title,options,duration));
    public void TwitchPredictionCancel(string predictionId)=>TwitchCall("TwitchPredictionCancel" ,predictionId);
    public void TwitchPredictionLock(string predictionId)=>TwitchCall("TwitchPredictionLock" ,predictionId);
    public void TwitchPredictionResolve(string predictionId,string winningId)=>TwitchCall("TwitchPredictionResolve" ,predictionId,winningId);
    public bool TwitchRunCommercial(int duration)=>TwitchCall("TwitchRunCommercial" ,duration).GetBoolean();
    public bool TwitchCancelRaid()=>TwitchCall("TwitchCancelRaid").GetBoolean();
    public bool TwitchShieldModeOn()=>TwitchCall("TwitchShieldModeOn").GetBoolean();
    public bool TwitchShieldModeOff()=>TwitchCall("TwitchShieldModeOff").GetBoolean();
    public int TwitchGetPrerollFreeTime()=>TwitchCall("TwitchGetPrerollFreeTime").GetInt32();
    public bool SendWhisper(string userName,string message,bool bot=true)=>TwitchCall("SendWhisper" ,userName,message,bot).GetBoolean();
    public bool TwitchUnpinMessage()=>TwitchCall("TwitchUnpinMessage").GetBoolean();
    public bool TwitchUpdatePinnedMessageDuration(int? duration=null)=>TwitchCall("TwitchUpdatePinnedMessageDuration" ,duration).GetBoolean();
    public bool TwitchPinChatMessage(string messageId,int? duration=null)=>TwitchCall("TwitchPinChatMessage" ,messageId,duration).GetBoolean();
    public bool SetChannelTitle(string title)=>TwitchCall("SetChannelTitle" ,title).GetBoolean();
    public bool SetChannelGameById(string gameId)=>TwitchCall("SetChannelGameById" ,gameId).GetBoolean();
    public bool TwitchAddModerator(string userName)=>TwitchCall("TwitchAddModerator" ,userName).GetBoolean();
    public bool TwitchRemoveModerator(string userName)=>TwitchCall("TwitchRemoveModerator" ,userName).GetBoolean();
    public bool TwitchAddVip(string userName)=>TwitchCall("TwitchAddVip" ,userName).GetBoolean();
    public bool TwitchRemoveVip(string userName)=>TwitchCall("TwitchRemoveVip" ,userName).GetBoolean();
    public bool TwitchBanUser(string userName,string reason=null,bool bot=false)=>TwitchCall("TwitchBanUser" ,userName,reason,bot).GetBoolean();
    public bool TwitchUnbanUser(string userName,bool bot=false)=>TwitchCall("TwitchUnbanUser" ,userName,bot).GetBoolean();
    public bool TwitchTimeoutUser(string username,int duration,string reason=null,bool bot=false)=>TwitchCall("TwitchTimeoutUser" ,username,duration,reason,bot).GetBoolean();
    public bool TwitchClearChatMessages(bool bot=true)=>TwitchCall("TwitchClearChatMessages" ,bot).GetBoolean();
    public bool TwitchDeleteChatMessage(string messageId,bool bot=true)=>TwitchCall("TwitchDeleteChatMessage" ,messageId,bot).GetBoolean();
    public void TwitchAnnounce(string message,bool bot=false,string color=null,bool fallback=false)=>TwitchCall("TwitchAnnounce" ,message,bot,color,fallback);
    public bool TwitchStartRaidById(string userId)=>TwitchCall("TwitchStartRaidById" ,userId).GetBoolean();
    public bool TwitchStartRaidByName(string userName)=>TwitchCall("TwitchStartRaidByName" ,userName).GetBoolean();
    public bool TwitchSendShoutoutById(string userId)=>TwitchCall("TwitchSendShoutoutById" ,userId).GetBoolean();
    public bool TwitchSendShoutoutByLogin(string userLogin)=>TwitchCall("TwitchSendShoutoutByLogin" ,userLogin).GetBoolean();
    public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo TwitchGetBroadcaster()=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo>(TwitchCall("TwitchGetBroadcaster"));
    public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo TwitchGetBot()=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo>(TwitchCall("TwitchGetBot"));
    public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo TwitchGetUserInfoById(string userId)=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo>(TwitchCall("TwitchGetUserInfoById" ,userId));
    public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo TwitchGetUserInfoByLogin(string userLogin)=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo>(TwitchCall("TwitchGetUserInfoByLogin" ,userLogin));
    public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfoEx TwitchGetExtendedUserInfoById(string userId)=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfoEx>(TwitchCall("TwitchGetExtendedUserInfoById" ,userId));
    public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfoEx TwitchGetExtendedUserInfoByLogin(string userLogin)=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfoEx>(TwitchCall("TwitchGetExtendedUserInfoByLogin" ,userLogin));
    public global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo> TwitchGetVips()=>Read<global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo>>(TwitchCall("TwitchGetVips"));
    public global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo> TwitchGetMods()=>Read<global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo>>(TwitchCall("TwitchGetMods"));
    public global::Streamer.bot.Plugin.Interface.Model.PinnedMessageData TwitchGetPinnedMessage()=>Read<global::Streamer.bot.Plugin.Interface.Model.PinnedMessageData>(TwitchCall("TwitchGetPinnedMessage"));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo> GetTeamInfo(int userId)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo>>(TwitchCall("GetTeamInfo" ,userId));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo> GetTeamInfo(string username)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo>>(TwitchCall("GetTeamInfo" ,username));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo> GetTeamInfoById(string userId)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo>>(TwitchCall("GetTeamInfoById" ,userId));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo> GetTeamInfoByLogin(string userLogin)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.TeamInfo>>(TwitchCall("GetTeamInfoByLogin" ,userLogin));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.Cheermote> GetCheermotes()=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.Cheermote>>(TwitchCall("GetCheermotes"));
    public global::Streamer.bot.Plugin.Interface.GameInfo SetChannelGame(string game)=>Read<global::Streamer.bot.Plugin.Interface.GameInfo>(TwitchCall("SetChannelGame" ,game));
    public global::Twitch.Common.Models.Api.ClipDownloadData TwitchGetClipDownloadUrls(string clipId)=>Read<global::Twitch.Common.Models.Api.ClipDownloadData>(TwitchCall("TwitchGetClipDownloadUrls" ,clipId));
    public global::Twitch.Common.Models.Api.StreamMarker CreateStreamMarker(string description)=>Read<global::Twitch.Common.Models.Api.StreamMarker>(TwitchCall("CreateStreamMarker" ,description));
    public global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.TwitchReward> TwitchGetRewards()=>Read<global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.TwitchReward>>(TwitchCall("TwitchGetRewards"));
    public bool TwitchIsUserSubscribed(string userId,out string tier){var reply=TwitchCall("TwitchIsUserSubscribed",userId);tier=reply.GetProperty("tier").GetString()!;return reply.GetProperty("subscribed").GetBoolean();}
    public global::Twitch.Common.Models.Api.GuestStarSettings TwitchGetChannelGuestStarSettings()=>Read<global::Twitch.Common.Models.Api.GuestStarSettings>(TwitchCall("TwitchGetChannelGuestStarSettings"));
    public bool TwitchUpdateChannelGuestStarSettings(bool? isModeratorSendLiveEnabled=null,int? slotCount=null,bool? isBrowserSourceAudioEnabled=null,string groupLayout=null,bool? regeneratgeBrowserSource=null)=>TwitchCall("TwitchUpdateChannelGuestStarSettings" ,isModeratorSendLiveEnabled,slotCount,isBrowserSourceAudioEnabled,groupLayout,regeneratgeBrowserSource).GetBoolean();
    public global::Twitch.Common.Models.Api.GuestSession TwitchGetGuestStarSession()=>Read<global::Twitch.Common.Models.Api.GuestSession>(TwitchCall("TwitchGetGuestStarSession"));
    public global::Twitch.Common.Models.Api.GuestSession TwitchCreateGuestStarSession()=>Read<global::Twitch.Common.Models.Api.GuestSession>(TwitchCall("TwitchCreateGuestStarSession"));
    public global::Twitch.Common.Models.Api.GuestSession TwitchEndGuestStarSession()=>Read<global::Twitch.Common.Models.Api.GuestSession>(TwitchCall("TwitchEndGuestStarSession"));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.GuestStarInvite> TwitchGetGuestStarInvites()=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.GuestStarInvite>>(TwitchCall("TwitchGetGuestStarInvites"));
    public bool TwitchSendGuestStarInvite(string userLogin)=>TwitchCall("TwitchSendGuestStarInvite" ,userLogin).GetBoolean();
    public bool TwitchDeleteGuestStarInvite(string userLogin)=>TwitchCall("TwitchDeleteGuestStarInvite" ,userLogin).GetBoolean();
    public bool TwitchAssignGuestStarSlot(string userLogin,int slot)=>TwitchCall("TwitchAssignGuestStarSlot" ,userLogin,slot).GetBoolean();
    public bool TwitchUpdateGuestStarSlot(int sourceSlot,int destinationSlot)=>TwitchCall("TwitchUpdateGuestStarSlot" ,sourceSlot,destinationSlot).GetBoolean();
    public bool TwitchDeleteGuestStarSlot(string userLogin,int slot)=>TwitchCall("TwitchDeleteGuestStarSlot" ,userLogin,slot).GetBoolean();
    public bool TwitchUpdateGuestStarSlotSettings(int slotId,bool? isAudioEnabled=null,bool? isVideoEnabled=null,bool? isLive=null,int? volume=null)=>TwitchCall("TwitchUpdateGuestStarSlotSettings" ,slotId,isAudioEnabled,isVideoEnabled,isLive,volume).GetBoolean();
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetAllClips(bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetAllClips",new Dictionary<string,object?>{{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClips(int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClips",new Dictionary<string,object?>{{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(int userId)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"userId",userId}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(int userId,int count)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"userId",userId},{"count",count}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(int userId,DateTime start,DateTime end)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"userId",userId},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(int userId,DateTime start,DateTime end,int count)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"userId",userId},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"count",count}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(int userId,global::System.TimeSpan duration)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"userId",userId},{"duration",duration.TotalSeconds}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(int userId,global::System.TimeSpan duration,int count)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"userId",userId},{"duration",duration.TotalSeconds},{"count",count}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUserById(string userId,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUserById",new Dictionary<string,object?>{{"userId",userId},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUserById(string userId,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUserById",new Dictionary<string,object?>{{"userId",userId},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUserById(string userId,DateTime start,DateTime end,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUserById",new Dictionary<string,object?>{{"userId",userId},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUserById(string userId,DateTime start,DateTime end,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUserById",new Dictionary<string,object?>{{"userId",userId},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUserById(string userId,global::System.TimeSpan duration,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUserById",new Dictionary<string,object?>{{"userId",userId},{"duration",duration.TotalSeconds},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUserById(string userId,global::System.TimeSpan duration,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUserById",new Dictionary<string,object?>{{"userId",userId},{"duration",duration.TotalSeconds},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(string username,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"username",username},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(string userName,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"userName",userName},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(string username,DateTime start,DateTime end,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"username",username},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(string username,DateTime start,DateTime end,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"username",username},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(string username,global::System.TimeSpan duration,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"username",username},{"duration",duration.TotalSeconds},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForUser(string username,global::System.TimeSpan duration,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForUser",new Dictionary<string,object?>{{"username",username},{"duration",duration.TotalSeconds},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForGame(int gameId,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForGame",new Dictionary<string,object?>{{"gameId",gameId},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForGame(int gameId,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForGame",new Dictionary<string,object?>{{"gameId",gameId},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForGame(int gameId,DateTime start,DateTime end,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForGame",new Dictionary<string,object?>{{"gameId",gameId},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForGame(int gameId,DateTime start,DateTime end,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForGame",new Dictionary<string,object?>{{"gameId",gameId},{"start",start.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"end",end.ToUniversalTime().ToString("O",System.Globalization.CultureInfo.InvariantCulture)},{"count",count},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForGame(int gameId,global::System.TimeSpan duration,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForGame",new Dictionary<string,object?>{{"gameId",gameId},{"duration",duration.TotalSeconds},{"isFeatured",isFeatured}}));
    public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData> GetClipsForGame(int gameId,global::System.TimeSpan duration,int count,bool? isFeatured=null)=>Read<global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.ClipData>>(TwitchCall("GetClipsForGame",new Dictionary<string,object?>{{"gameId",gameId},{"duration",duration.TotalSeconds},{"count",count},{"isFeatured",isFeatured}}));
    public global::Twitch.Common.Models.Api.ClipData CreateClip(string title=null,int duration=30)=>Read<global::Twitch.Common.Models.Api.ClipData>(TwitchCall("CreateClip",title,duration));
    public bool TwitchBlockUser(string userLogin,global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockContext context=global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockContext.None,global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockReason reason=global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockReason.None)=>TwitchCall("TwitchBlockUser" ,userLogin,context,reason).GetBoolean();
    public bool TwitchBlockUserById(string userId,global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockContext context=global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockContext.None,global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockReason reason=global::Streamer.bot.Plugin.Interface.Enums.TwitchBlockReason.None)=>TwitchCall("TwitchBlockUserById" ,userId,context,reason).GetBoolean();
    public bool TwitchUnblockUser(string userLogin)=>TwitchCall("TwitchUnblockUser" ,userLogin).GetBoolean();
    public bool TwitchUnblockUserById(string userId)=>TwitchCall("TwitchUnblockUserById" ,userId).GetBoolean();
    public bool TwitchApproveAutoHeldMessage(string messageId)=>TwitchCall("TwitchApproveAutoHeldMessage" ,messageId).GetBoolean();
    public bool TwitchDenyAutoHeldMessage(string messageId)=>TwitchCall("TwitchDenyAutoHeldMessage" ,messageId).GetBoolean();
    public bool TwitchAddBlockedTerm(string term)=>TwitchCall("TwitchAddBlockedTerm" ,term).GetBoolean();
    public bool TwitchRemoveBlockedTerm(string term)=>TwitchCall("TwitchRemoveBlockedTerm" ,term).GetBoolean();
    public global::System.Collections.Generic.List<string> TwitchGetBlockedTerms()=>Read<global::System.Collections.Generic.List<string>>(TwitchCall("TwitchGetBlockedTerms"));
    public long TwitchGetChannelPointsUsedByUserId(string userId)=>TwitchCall("TwitchGetChannelPointsUsedByUserId" ,userId).GetInt64();
    public void TwitchResetRewardCounter(string rewardId)=>TwitchCall("TwitchResetRewardCounter" ,rewardId);
    public void TwitchResetRewardUserCounters(string rewardId)=>TwitchCall("TwitchResetRewardUserCounters" ,rewardId);
    public void TwitchResetUserRewardCounters(string userId,bool persisted)=>TwitchCall("TwitchResetUserRewardCounters" ,userId,persisted);
    public void TwitchResetUserRewardCounter(string rewardId,string userId)=>TwitchCall("TwitchResetUserRewardCounter" ,rewardId,userId);
    public global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter TwitchGetRewardCounter(string rewardId,bool persisted=true)=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter>(TwitchCall("TwitchGetRewardCounter" ,rewardId,persisted));
    public global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter TwitchGetRewardUserCounter(string userLogin,string rewardId,bool persisted=true)=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter>(TwitchCall("TwitchGetRewardUserCounter" ,userLogin,rewardId,persisted));
    public global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter TwitchGetRewardUserCounterById(string userId,string rewardId,bool persisted=true)=>Read<global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter>(TwitchCall("TwitchGetRewardUserCounterById" ,userId,rewardId,persisted));
    public global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter> TwitchGetRewardUserCounters(string rewardId,bool persisted=true)=>Read<global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.Model.TwitchRewardCounter>>(TwitchCall("TwitchGetRewardUserCounters" ,rewardId,persisted));
    public long TwitchGetBitsDonatedByUserId(string userId)=>TwitchCall("TwitchGetBitsDonatedByUserId" ,userId).GetInt64();
    private JsonElement ObsCall(string operation,int connection,params object?[] values)=>Rpc("obs_csharp",operation,connection,values);
    public int ObsGetConnectionByName(string name)
    {
        var rows=ObsCall("names",0).Deserialize<List<string?>>()!;if(rows.Count==0)return -1;
        int index=0;foreach(var row in rows){if(string.Equals(row,name,StringComparison.OrdinalIgnoreCase))break;index++;}return index;
    }
    public long ObsConvertRgb(int a,int r,int g,int b)=>Convert.ToInt64(string.Format("{0:X2}{1:X2}{2:X2}{3:X2}",a,b,g,r),16);
    public long ObsConvertColorHex(string colorHex)
    {
        if(colorHex==null || !System.Text.RegularExpressions.Regex.IsMatch(colorHex,"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$"))return 0;
        try{var c=System.Drawing.ColorTranslator.FromHtml(colorHex);return ObsConvertRgb(c.A,c.R,c.G,c.B);}catch{return 0;}
    }
    public bool ObsIsConnected(int connection=0)=>ObsCall("ObsIsConnected",connection).GetBoolean();
    public bool ObsConnect(int connection=0)=>ObsCall("ObsConnect",connection).GetBoolean();
    public void ObsDisconnect(int connection=0)=>ObsCall("ObsDisconnect",connection);
    public bool ObsIsStreaming(int connection=0)=>ObsCall("ObsIsStreaming",connection).GetBoolean();
    public void ObsStopStreaming(int connection=0)=>ObsCall("ObsStopStreaming",connection);
    public void ObsStartStreaming(int connection=0)=>ObsCall("ObsStartStreaming",connection);
    public bool ObsIsRecording(int connection=0)=>ObsCall("ObsIsRecording",connection).GetBoolean();
    public void ObsStartRecording(int connection=0)=>ObsCall("ObsStartRecording",connection);
    public void ObsStopRecording(int connection=0)=>ObsCall("ObsStopRecording",connection);
    public void ObsPauseRecording(int connection=0)=>ObsCall("ObsPauseRecording",connection);
    public void ObsResumeRecording(int connection=0)=>ObsCall("ObsResumeRecording",connection);
    public void ObsSetScene(string sceneName,int connection=0)=>ObsCall("ObsSetScene",connection ,sceneName);
    public string ObsGetCurrentScene(int connection=0)=>Read<string>(ObsCall("ObsGetCurrentScene",connection));
    public bool ObsIsSourceVisible(string scene,string source,int connection=0)=>ObsCall("ObsIsSourceVisible",connection ,scene,source).GetBoolean();
    public void ObsSetSourceVisibility(string scene,string source,bool visible,int connection=0)=>ObsCall("ObsSetSourceVisibility",connection ,scene,source,visible);
    public void ObsSetSourceVisibilityState(string scene,string source,int state,int connection=0)=>ObsCall("ObsSetSourceVisibilityState",connection ,scene,source,state);
    public void ObsShowSource(string scene,string source,int connection=0)=>ObsCall("ObsShowSource",connection ,scene,source);
    public void ObsHideSource(string scene,string source,int connection=0)=>ObsCall("ObsHideSource",connection ,scene,source);
    public void ObsHideGroupsSources(string scene,string groupName,int connection=0)=>ObsCall("ObsHideGroupsSources",connection ,scene,groupName);
    public string ObsSetRandomGroupSourceVisible(string scene,string groupName,int connection=0)=>Read<string>(ObsCall("ObsSetRandomGroupSourceVisible",connection ,scene,groupName));
    public List<string> ObsGetGroupSources(string scene,string groupName,int connection=0)=>Read<List<string>>(ObsCall("ObsGetGroupSources",connection ,scene,groupName));
    public void ObsSetBrowserSource(string scene,string source,string url,int connection=0)=>ObsCall("ObsSetBrowserSource",connection ,scene,source,url);
    public void ObsSetGdiText(string scene,string source,string text,int connection=0)=>ObsCall("ObsSetGdiText",connection ,scene,source,text);
    public bool ObsIsFilterEnabled(string scene,string filterName,int connection=0)=>ObsCall("ObsIsFilterEnabled",connection ,scene,filterName).GetBoolean();
    public bool ObsIsFilterEnabled(string scene,string source,string filterName,int connection=0)=>ObsCall("ObsIsFilterEnabled",connection ,scene,source,filterName).GetBoolean();
    public void ObsSetFilterState(string scene,string filterName,int state,int connection=0)=>ObsCall("ObsSetFilterState",connection ,scene,filterName,state);
    public void ObsSetFilterState(string scene,string source,string filterName,int state,int connection=0)=>ObsCall("ObsSetFilterState",connection ,scene,source,filterName,state);
    public void ObsShowFilter(string scene,string filterName,int connection=0)=>ObsCall("ObsShowFilter",connection ,scene,filterName);
    public void ObsShowFilter(string scene,string source,string filterName,int connection=0)=>ObsCall("ObsShowFilter",connection ,scene,source,filterName);
    public void ObsHideFilter(string scene,string filterName,int connection=0)=>ObsCall("ObsHideFilter",connection ,scene,filterName);
    public void ObsHideFilter(string scene,string source,string filterName,int connection=0)=>ObsCall("ObsHideFilter",connection ,scene,source,filterName);
    public void ObsHideSourcesFilters(string scene,string source,int connection=0)=>ObsCall("ObsHideSourcesFilters",connection ,scene,source);
    public void ObsHideScenesFilters(string scene,int connection=0)=>ObsCall("ObsHideScenesFilters",connection ,scene);
    public void ObsToggleFilter(string scene,string filterName,int connection=0)=>ObsCall("ObsToggleFilter",connection ,scene,filterName);
    public void ObsToggleFilter(string scene,string source,string filterName,int connection=0)=>ObsCall("ObsToggleFilter",connection ,scene,source,filterName);
    public void ObsSetRandomFilterState(string scene,int state,int connection=0)=>ObsCall("ObsSetRandomFilterState",connection ,scene,state);
    public void ObsSetRandomFilterState(string scene,string source,int state,int connection=0)=>ObsCall("ObsSetRandomFilterState",connection ,scene,source,state);
    public void ObsSetSourceMuteState(string scene,string source,int state,int connection=0)=>ObsCall("ObsSetSourceMuteState",connection ,scene,source,state);
    public void ObsSourceMute(string scene,string source,int connection=0)=>ObsCall("ObsSourceMute",connection ,scene,source);
    public void ObsSourceUnMute(string scene,string source,int connection=0)=>ObsCall("ObsSourceUnMute",connection ,scene,source);
    public void ObsSourceMuteToggle(string scene,string source,int connection=0)=>ObsCall("ObsSourceMuteToggle",connection ,scene,source);
    private JsonElement YouTubeCall(string method,params object?[] values)=>Rpc("youtube_csharp",method,values);
    public void SendYouTubeMessage(string message,bool useBot=true,bool fallback=true,string broadcastId=null)=>YouTubeCall("SendYouTubeMessage",message,useBot,fallback,broadcastId);
    public void SendYouTubeMessageToLatestMonitored(string message,bool useBot=true,bool fallback=true)=>YouTubeCall("SendYouTubeMessageToLatestMonitored",message,useBot,fallback);
    public int AddQuoteForYouTube(string userId,string quote)=>Read<int>(YouTubeCall("AddQuoteForYouTube",userId,quote));
    public YouTubeUserInfo YouTubeGetBroadcaster()=>Read<YouTubeUserInfo>(YouTubeCall("YouTubeGetBroadcaster"));
    public YouTubeUserInfo YouTubeGetBot()=>Read<YouTubeUserInfo>(YouTubeCall("YouTubeGetBot"));
    public YouTubeBroadcastInfo YouTubeGetLatestMonitoredBroadcast()=>Read<YouTubeBroadcastInfo>(YouTubeCall("YouTubeGetLatestMonitoredBroadcast"));
    public List<YouTubeBroadcastInfo> YouTubeGetMonitoredBroadcasts()=>Read<List<YouTubeBroadcastInfo>>(YouTubeCall("YouTubeGetMonitoredBroadcasts"));
    public bool YouTubeSetTitle(string title,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeSetTitle",title,broadcastId));
    public bool YouTubeSetDescription(string description,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeSetDescription",description,broadcastId));
    public bool YouTubeSetPrivacy(string privacy,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeSetPrivacy",privacy,broadcastId));
    public bool YouTubeSetCategory(string categoryName,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeSetCategory",categoryName,broadcastId));
    public bool YouTubeSetMetaData(string title,string description,string privacy,string categoryName,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeSetMetaData",title,description,privacy,categoryName,broadcastId));
    public bool YouTubeClearTags(string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeClearTags",broadcastId));
    public bool YouTubeAddTags(List<string> tags,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeAddTags",tags,broadcastId));
    public bool YouTubeRemoveTags(List<string> tags,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeRemoveTags",tags,broadcastId));
    public bool YouTubeTimeoutUserById(string userId,int duration,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeTimeoutUserById",userId,duration,broadcastId));
    public bool YouTubeTimeoutUserByName(string userName,int duration,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeTimeoutUserByName",userName,duration,broadcastId));
    public bool YouTubeBanUserById(string userId,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeBanUserById",userId,broadcastId));
    public bool YouTubeBanUserByName(string userName,string broadcastId=null)=>Read<bool>(YouTubeCall("YouTubeBanUserByName",userName,broadcastId));
    public string ObsSendRaw(string requestType,string data,int connection=0)=>Read<string>(ObsCall("ObsSendRaw",connection ,requestType,data));
    public string ObsSendBatchRaw(string data,bool haltOnFailure=false,int executionType=0,int connection=0)=>Read<string>(ObsCall("ObsSendBatchRaw",connection ,data,haltOnFailure,executionType));
    public void ObsSetMediaState(string scene,string source,int state,int connection=0)=>ObsCall("ObsSetMediaState",connection ,scene,source,state);
    public void ObsMediaPlay(string scene,string source,int connection=0)=>ObsCall("ObsMediaPlay",connection ,scene,source);
    public void ObsMediaPause(string scene,string source,int connection=0)=>ObsCall("ObsMediaPause",connection ,scene,source);
    public void ObsMediaRestart(string scene,string source,int connection=0)=>ObsCall("ObsMediaRestart",connection ,scene,source);
    public void ObsMediaStop(string scene,string source,int connection=0)=>ObsCall("ObsMediaStop",connection ,scene,source);
    public void ObsMediaNext(string scene,string source,int connection=0)=>ObsCall("ObsMediaNext",connection ,scene,source);
    public void ObsMediaPrevious(string scene,string source,int connection=0)=>ObsCall("ObsMediaPrevious",connection ,scene,source);
    public void ObsSetReplayBufferState(int state,int connection=0)=>ObsCall("ObsSetReplayBufferState",connection ,state);
    public void ObsReplayBufferStart(int connection=0)=>ObsCall("ObsReplayBufferStart",connection);
    public void ObsReplayBufferStop(int connection=0)=>ObsCall("ObsReplayBufferStop",connection);
    public void ObsReplayBufferSave(int connection=0)=>ObsCall("ObsReplayBufferSave",connection);
    public void ObsSetMediaSourceFile(string scene,string source,string file,int connection=0)=>ObsCall("ObsSetMediaSourceFile",connection ,scene,source,file);
    public void ObsSetImageSourceFile(string scene,string source,string file,int connection=0)=>ObsCall("ObsSetImageSourceFile",connection ,scene,source,file);
    public string ObsGetSceneItemProperties(string scene,string source,int connection=0)=>Read<string>(ObsCall("ObsGetSceneItemProperties",connection ,scene,source));
    public void ObsHideSceneSources(string scene,int connection=0)=>ObsCall("ObsHideSceneSources",connection ,scene);
    public string ObsSetRandomSceneSourceVisible(string scene,int connection=0)=>Read<string>(ObsCall("ObsSetRandomSceneSourceVisible",connection ,scene));
    public bool ObsTakeScreenshot(string source,string path,int quality=-1,int connection=0)=>ObsCall("ObsTakeScreenshot",connection ,source,path,quality).GetBoolean();
    public void ObsSetColorSourceColor(string scene,string source,int a,int r,int g,int b,int connection=0)=>ObsCall("ObsSetColorSourceColor",connection ,scene,source,ObsConvertRgb(a,r,g,b));
    public void ObsSetColorSourceColor(string scene,string source,string hexColor,int connection=0)=>ObsCall("ObsSetColorSourceColor",connection ,scene,source,ObsConvertColorHex(hexColor));
    public void ObsSetColorSourceRandomColor(string scene,string source,int connection=0)=>ObsCall("ObsSetColorSourceRandomColor",connection ,scene,source);
    public bool ObsCreateRecordChapter(string chapterName,int connection=0)=>ObsCall("ObsCreateRecordChapter",connection ,chapterName).GetBoolean();
    private Guid? MidiDeviceByName(string name)
    {
        if(string.IsNullOrWhiteSpace(name))return null;
        foreach(var row in Rpc("midi_devices").EnumerateArray())
            if(string.Equals(row.GetProperty("name").GetString(),name,StringComparison.OrdinalIgnoreCase))return Guid.Parse(row.GetProperty("id").GetString()!);
        return null;
    }
    private bool MidiValues(int channel,int data1,int data2)=>channel>=1 && channel<=16 && data1>=0 && data1<=127 && data2>=0 && data2<=127;
    public void MidiSendRaw(Guid deviceId,int command,int channel,int data1,int data2)
    {
        if(command<0 || command>255 || !MidiValues(channel,data1,data2))return;
        Rpc("midi_send",deviceId,command,channel,data1,data2,0,false);
    }
    public void MidiSendRawByName(string name,int command,int channel,int data1,int data2)
    {
        var id=MidiDeviceByName(name);if(id.HasValue)MidiSendRaw(id.Value,command,channel,data1,data2);
    }
    public void MidiSendControlChange(Guid deviceId,int channel,int controller,int value)=>MidiSendRaw(deviceId,176,channel,controller,value);
    public void MidiSendControlChangeByName(string name,int channel,int controller,int value)
    {
        var id=MidiDeviceByName(name);if(id.HasValue)MidiSendControlChange(id.Value,channel,controller,value);
    }
    public void MidiSendNoteOn(Guid deviceId,int channel,int note,int velocity,int duration=0,bool sendNoteOff=false)
    {
        if(!MidiValues(channel,note,velocity))return;
        Rpc("midi_send",deviceId,144,channel,note,velocity,duration,sendNoteOff);
    }
    public void MidiSendNoteOnByName(string name,int channel,int note,int velocity,int duration=0,bool sendNoteOff=false)
    {
        var id=MidiDeviceByName(name);if(id.HasValue)MidiSendNoteOn(id.Value,channel,note,velocity,duration,sendNoteOff);
    }
    private float SoundVolume(float volume)
    {
        if(!float.IsFinite(volume) || volume<0 || volume>1)throw new ArgumentOutOfRangeException(nameof(volume));
        return volume;
    }
    public double PlaySound(string fileName,float volume=1,bool finishBeforeContinuing=false,string? name=null,bool useFileName=true)=>Rpc("sound_play","file",fileName,SoundVolume(volume),false,finishBeforeContinuing,name,useFileName).GetDouble();
    public double PlaySoundFromFolder(string path,float volume=1,bool recursive=false,bool finishBeforeContinuing=false,string? name=null,bool useFileName=true)=>Rpc("sound_play","folder",path,SoundVolume(volume),recursive,finishBeforeContinuing,name,useFileName).GetDouble();
    public void StopSoundPlayback(string soundName)=>Rpc("sound_stop",soundName);
    public void StopAllSoundPlayback()=>Rpc("sound_stop_all");
    public void WebsocketBroadcastString(string data)=>Rpc("websocket_broadcast","string",data);
    public void WebsocketBroadcastJson(string data)
    {
        ArgumentNullException.ThrowIfNull(data);
        using var document=JsonDocument.Parse(data);
        if(document.RootElement.ValueKind!=JsonValueKind.Object)throw new JsonException("Broadcast JSON must be an object");
        Rpc("websocket_broadcast","json",document.RootElement.GetRawText());
    }
    private JsonElement WebsocketServer(string operation,int connection,object? data=null,string? session=null)
    {
        var reply=Rpc("websocket_server",operation,connection,data,session);
        if(reply.ValueKind==JsonValueKind.Object && reply.TryGetProperty("invalidIndex",out _))throw new ArgumentOutOfRangeException("index");
        return reply;
    }
    public void WebsocketCustomServerStart(int connection=0)=>WebsocketServer("start",connection);
    public void WebsocketCustomServerStop(int connection=0)=>WebsocketServer("stop",connection);
    public bool WebsocketCustomServerIsListening(int connection=0)=>WebsocketServer("listening",connection).GetBoolean();
    public void WebsocketCustomServerCloseAllSessions(int connection=0)=>WebsocketServer("close_all",connection);
    public void WebsocketCustomServerCloseSession(string sessionId,int connection=0)=>WebsocketServer("close",connection,null,sessionId);
    public void WebsocketCustomServerBroadcast(string data,string? sessionId,int connection=0)=>WebsocketServer("broadcast",connection,data,sessionId);
    public void WebsocketCustomServerBroadcast(string data,int connection=0)=>WebsocketCustomServerBroadcast(data,null,connection);
    public int WebsocketCustomServerGetConnectionByName(string name)
    {
        var names=Rpc("websocket_server","names").Deserialize<List<string?>>()!;
        if(names.Count==0)return -1;
        int index=0;foreach(var current in names){if(string.Equals(current,name,StringComparison.OrdinalIgnoreCase))break;index++;}
        return index;
    }
    private JsonElement WebsocketClient(string operation,int connection,object? data=null)
    {
        var reply=Rpc("websocket_client",operation,connection,data);
        if(reply.ValueKind==JsonValueKind.Object && reply.TryGetProperty("invalidIndex",out var invalid) && invalid.GetBoolean())throw new ArgumentOutOfRangeException("index");
        return reply;
    }
    public void WebsocketConnect(int connection=0)=>WebsocketClient("connect",connection);
    public void WebsocketDisconnect(int connection=0)=>WebsocketClient("disconnect",connection);
    public bool WebsocketIsConnected(int connection=0)=>WebsocketClient("connected",connection).GetBoolean();
    public void WebsocketSend(string data,int connection=0)=>WebsocketClient("send_text",connection,data);
    public void WebsocketSend(byte[] data,int connection=0)=>WebsocketClient("send_bytes",connection,data);
    public QuoteData GetQuote(int quoteId)
    {
        var quote=Rpc("quote_get",quoteId);
        if(quote.ValueKind==JsonValueKind.Null)throw new NullReferenceException();
        return quote.Deserialize<QuoteData>()!;
    }
    public int GetQuoteCount()=>Rpc("quote_count").GetInt32();
    public bool DeleteQuote(int quoteId)=>Rpc("quote_delete",quoteId).GetBoolean();
    public int AddQuoteForTwitch(string userId,string quote,bool captureGame=false)=>Rpc("quote_add_twitch",userId,quote,captureGame).GetInt32();
    [Obsolete("Trovo support has been removed; this method returns -1 without creating a quote.")]
    public int AddQuoteForTrovo(string userId,string quote,bool captureGame=false)=>-1;
    public string GetVersion()=>Rpc("runtime_version").GetString()!;
    public string EscapeString(string text)=>RegexEscapeText.Replace(text,"\\$1");
    public string? UrlEncode(string text)=>System.Net.WebUtility.UrlEncode(text);
    public int Between(int min,int max)
    {
        if(min>max)throw new ArgumentOutOfRangeException(nameof(min),"min must not exceed max");
        if(min==max)return min;
        ulong range=(ulong)((long)max-min+1);
        ulong ceiling=1UL<<32;
        ulong limit=ceiling-ceiling%range;
        Span<byte> bytes=stackalloc byte[4];
        uint sample;
        do { System.Security.Cryptography.RandomNumberGenerator.Fill(bytes);sample=BitConverter.ToUInt32(bytes); } while(sample>=limit);
        return (int)((long)min+(long)((ulong)sample%range));
    }
    public double NextDouble()
    {
        Span<byte> bytes=stackalloc byte[8];
        System.Security.Cryptography.RandomNumberGenerator.Fill(bytes);
        return (BitConverter.ToUInt64(bytes)&0x7fffffffffffffffUL)/9223372036854775808.0;
    }
    public void Wait(int milliseconds)=>Rpc("wait",milliseconds);
    public void LogVerbose(string logLine)=>Rpc("log","verbose",logLine);
    public bool ActionExists(string actionName)=>Rpc("action_exists",actionName).GetBoolean();
    public void DisableAction(string actionName)=>Rpc("action_enabled",actionName,false,false);
    public void DisableActionById(string actionId)=>Rpc("action_enabled",actionId,true,false);
    public void EnableAction(string actionName)=>Rpc("action_enabled",actionName,false,true);
    public void EnableActionById(string actionId)=>Rpc("action_enabled",actionId,true,true);
    public List<ActionData> GetActions()=>Rpc("actions_list").Deserialize<List<ActionData>>()!;
    public void PauseActionQueue(string name)=>Rpc("queue_control",name,true,false,false);
    public void PauseAllActionQueues()=>Rpc("queue_control",null,true,false,true);
    public void ResumeActionQueue(string name,bool clear=false)=>Rpc("queue_control",name,false,clear,false);
    public void ResumeAllActionQueues(bool clear=false)=>Rpc("queue_control",null,false,clear,true);
    public void ClearNonPersistedGlobals()=>Rpc("globals_clear",false);
    public void ClearNonPersistedUserGlobals()=>Rpc("globals_clear",true);
    public List<GlobalVariableValue> GetGlobalVarValues(bool persisted=true)=>Rpc("globals_list",persisted).Deserialize<List<GlobalVariableValue>>(ValueOptions)!;
    public void UnsetAllUsersVar(string varName,bool persisted=true)=>Rpc("all_users_unset",varName,persisted);
    public T GetTwitchUserVar<T>(string userName,string varName,bool persisted=true)=>Read<T>(Rpc("twitch_var","get",userName,false,varName,null,persisted));
    public T GetTwitchUserVarById<T>(string userId,string varName,bool persisted=true)=>Read<T>(Rpc("twitch_var","get",userId,true,varName,null,persisted));
    public void SetTwitchUserVar(string userName,string varName,object? value,bool persisted=true)=>Rpc("twitch_var","set",userName,false,varName,value,persisted);
    public void SetTwitchUserVarById(string userId,string varName,object? value,bool persisted=true)=>Rpc("twitch_var","set",userId,true,varName,value,persisted);
    public void UnsetTwitchUserVar(string userName,string varName,bool persisted=true)=>Rpc("twitch_var","unset",userName,false,varName,null,persisted);
    public void UnsetTwitchUserVarById(string userId,string varName,bool persisted=true)=>Rpc("twitch_var","unset",userId,true,varName,null,persisted);
    public void UnsetTwitchUser(string userName,bool persisted=true)=>Rpc("twitch_var","unset_user",userName,false,null,null,persisted);
    public void UnsetTwitchUserById(string userId,bool persisted=true)=>Rpc("twitch_var","unset_user",userId,true,null,null,persisted);
    public List<UserVariableValue<T>> GetTwitchUsersVar<T>(string varName,bool persisted=true)=>Rpc("twitch_vars_list",varName,persisted).Deserialize<List<UserVariableValue<T>>>(ValueOptions)!;
    public void SetTwitchUsersVarById(List<string> userIds,string varName,object? value,bool persisted=true)=>Rpc("twitch_vars_bulk","set",userIds,varName,value,persisted);
    public void IncrementTwitchUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("twitch_vars_bulk","increment",userIds,varName,value,persisted);
    public void IncrementOrCreateTwitchUsersVarById(List<string> userIds,string varName,object value,bool persisted=true)=>Rpc("twitch_vars_bulk","increment_create",userIds,varName,value,persisted);
    public void IncrementAllTwitchUsersVar(string varName,object value,bool persisted=true)=>Rpc("twitch_vars_bulk","all_increment",null,varName,value,persisted);
    public bool ResetPointDefinition(Guid pointId)=>Rpc("points_admin_reset",pointId).GetBoolean();
    public int AwardPointsToAll(Guid pointId,long amount,bool onlyActive,Platform? platform=null,bool useMultipliers=false)=>Rpc("points_award",pointId,amount,onlyActive,platform.HasValue?(int)platform.Value:null,useMultipliers,null).GetInt32();
    public int AwardPointsToGroup(string groupName,Guid pointId,long amount,bool useMultipliers=false)=>Rpc("points_award",pointId,amount,false,null,useMultipliers,groupName).GetInt32();
    public double GetGroupMultiplier(Guid pointId,string groupName)=>Rpc("points_group_multiplier","get",pointId,groupName,null).GetDouble();
    public bool SetGroupMultiplier(Guid pointId,string groupName,double multiplier)=>Rpc("points_group_multiplier","set",pointId,groupName,multiplier).GetBoolean();
    public bool RemoveGroupMultiplier(Guid pointId,string groupName)=>Rpc("points_group_multiplier","remove",pointId,groupName,null).GetBoolean();
    public long GetPoints(string userName,Platform platform,Guid pointId)=>Rpc("points_user","get",userName,(int)platform,pointId,0,false).GetInt64();
    public double GetUserMultiplier(string userName,Platform platform,Guid pointId)=>Rpc("points_user","multiplier",userName,(int)platform,pointId,0,false).GetDouble();
    public bool ResetUserPoints(string userName,Platform platform,Guid pointId)=>Rpc("points_user","reset",userName,(int)platform,pointId,0,false).GetBoolean();
    public bool DeletePoints(string userName,Platform platform,Guid pointId)=>Rpc("points_user","delete",userName,(int)platform,pointId,0,false).GetBoolean();
    public bool AddPoints(string userName,Platform platform,Guid pointId,long amount,bool useMultipliers=false)=>Rpc("points_user","add",userName,(int)platform,pointId,amount,useMultipliers).GetBoolean();
    public bool UpdatePoints(string userName,Platform platform,Guid pointId,long amount,bool useMultipliers=false)=>Rpc("points_user","update",userName,(int)platform,pointId,amount,useMultipliers).GetBoolean();
    public bool SetPoints(string userName,Platform platform,Guid pointId,long amount)=>Rpc("points_user","set",userName,(int)platform,pointId,amount,false).GetBoolean();
    public bool RemovePoints(string userName,Platform platform,Guid pointId,long amount)=>Rpc("points_user","remove",userName,(int)platform,pointId,amount,false).GetBoolean();
    public bool SpendPoints(string userName,Platform platform,Guid pointId,long cost)=>Rpc("points_user","spend",userName,(int)platform,pointId,cost,false).GetBoolean();
    public bool HasPoints(string userName,Platform platform,Guid pointId,long cost)=>Rpc("points_user","has",userName,(int)platform,pointId,cost,false).GetBoolean();
    public Dictionary<string,long> GetPointsForUsers(List<string> userNames,Platform platform,Guid pointId)=>Rpc("points_get_many",userNames,(int)platform,pointId).Deserialize<Dictionary<string,long>>()!;
    public bool UpdateBulkPoints(List<string> userNames,Platform platform,Guid pointId,long pointsDelta)=>Rpc("points_bulk",userNames,(int)platform,pointId,pointsDelta).GetBoolean();
    public bool TransferPoints(string sourceUserName,string destUserName,Platform platform,Guid pointId,long amount)=>Rpc("points_transfer",sourceUserName,destUserName,(int)platform,pointId,amount).GetBoolean();
    public List<string> GetGroups()=>Rpc("groups_list").Deserialize<List<string>>()!;
    public bool GroupExists(string groupName)=>Rpc("group_exists",groupName).GetBoolean();
    public bool AddGroup(string groupName)=>Rpc("group_add",groupName).GetBoolean();
    public bool DeleteGroup(string groupName)=>Rpc("group_delete",groupName).GetBoolean();
    public bool ClearUsersFromGroup(string groupName)=>Rpc("group_clear",groupName).GetBoolean();
    public List<GroupUser> UsersInGroup(string groupName)=>Rpc("group_users",groupName).Deserialize<List<GroupUser>>()!;
    public bool AddUserToGroup(string userName,Platform platform,string groupName)=>Rpc("group_user","add",userName,(int)platform,groupName,false).GetBoolean();
    public bool AddUserIdToGroup(string userId,Platform platform,string groupName)=>Rpc("group_user","add",userId,(int)platform,groupName,true).GetBoolean();
    public bool RemoveUserFromGroup(string userName,Platform platform,string groupName)=>Rpc("group_user","remove",userName,(int)platform,groupName,false).GetBoolean();
    public bool RemoveUserIdFromGroup(string userId,Platform platform,string groupName)=>Rpc("group_user","remove",userId,(int)platform,groupName,true).GetBoolean();
    public bool UserInGroup(string userName,Platform platform,string groupName)=>Rpc("group_user","contains",userName,(int)platform,groupName,false).GetBoolean();
    public bool UserIdInGroup(string userId,Platform platform,string groupName)=>Rpc("group_user","contains",userId,(int)platform,groupName,true).GetBoolean();
    public void DisableTimer(string timerName)=>Rpc("timer_enabled",timerName,false,false);
    public void DisableTimerById(string timerId)=>Rpc("timer_enabled",timerId,true,false);
    public void EnableTimer(string timerName)=>Rpc("timer_enabled",timerName,false,true);
    public void EnableTimerById(string timerId)=>Rpc("timer_enabled",timerId,true,true);
    public bool GetTimerState(string timerId)=>Rpc("timer_state",timerId).GetBoolean();
    public void SetTimerInterval(string timerId,int interval)=>Rpc("timer_interval",timerId,interval);
    public List<CommandData> GetCommands()=>Rpc("commands_list").Deserialize<List<CommandData>>()!;
    public void EnableCommand(string id)=>Rpc("command_enabled",id,true);
    public void DisableCommand(string id)=>Rpc("command_enabled",id,false);
    public int CommandGetCounter(string commandId)=>Rpc("command_counter",commandId).GetInt32();
    public CommandCounter? CommandGetUserCounter(string userLogin,Platform platform,string commandId)=>Rpc("command_user_counter",userLogin,(int)platform,commandId,false).Deserialize<CommandCounter>();
    public CommandCounter? CommandGetUserCounterById(string userId,Platform platform,string commandId)=>Rpc("command_user_counter",userId,(int)platform,commandId,true).Deserialize<CommandCounter>();
    public void CommandResetCounter(string commandId)=>Rpc("command_reset_counter",commandId);
    public void CommandResetAllUserCounters(string commandId)=>Rpc("command_reset_users",commandId,null,null,null);
    public void CommandResetUserCounter(string commandId,string userId,Platform platform)=>Rpc("command_reset_users",commandId,userId,(int)platform,null);
    public void CommandResetUsersCounters(string userId,Platform platform,bool persisted)=>Rpc("command_reset_users",null,userId,(int)platform,persisted);
    public void CommandSetGlobalCooldownDuration(string id,int seconds)=>Rpc("command_duration",id,"globalCooldown",seconds);
    public void CommandSetUserCooldownDuration(string id,int seconds)=>Rpc("command_duration",id,"userCooldown",seconds);
    public void CommandAddToGlobalCooldown(string id,int seconds)=>Rpc("command_cooldown","add",id,null,null,seconds);
    public void CommandRemoveGlobalCooldown(string id)=>Rpc("command_cooldown","remove",id);
    public void CommandResetGlobalCooldown(string id)=>Rpc("command_cooldown","reset",id);
    public void CommandAddToUserCooldown(string id,string userId,Platform platform,int seconds)=>Rpc("command_cooldown","add",id,userId,(int)platform,seconds);
    public void CommandRemoveUserCooldown(string id,string userId,Platform platform)=>Rpc("command_cooldown","remove",id,userId,(int)platform);
    public void CommandResetUserCooldown(string id,string userId,Platform platform)=>Rpc("command_cooldown","reset",id,userId,(int)platform);
    public void CommandAddToAllUserCooldowns(string id,int seconds)=>Rpc("command_cooldown","all_add",id,null,null,seconds);
    public void CommandRemoveAllUserCooldowns(string id)=>Rpc("command_cooldown","all_remove",id);
    public void CommandResetAllUserCooldowns(string id)=>Rpc("command_cooldown","all_reset",id);
    [Obsolete("Deprecated in Streamer.bot v0.2.3; this integer-userId overload has no effect. Use string userId and Platform.")]
    public void CommandResetUserCooldown(string id,int userId) { }
    [Obsolete("Deprecated in Streamer.bot v0.2.3; this integer-userId overload has no effect. Use string userId and Platform.")]
    public void CommandRemoveUserCooldown(string id,int userId) { }
    [Obsolete("Deprecated in Streamer.bot v0.2.3; this integer-userId overload has no effect. Use string userId and Platform.")]
    public void CommandAddToUserCooldown(string id,int userId,int seconds) { }
    public bool ExecuteMethod(string executeCode,string methodName)
    {
        var reply=Rpc("execute_method",executeCode,methodName,args,codeId);
        if(reply.TryGetProperty("local",out var local) && local.GetBoolean())
        {
            if(LocalMethod==null)throw new Exception("Local code method is unavailable");
            if(localDepth>=20)throw new Exception("Zyklischer C#-Methodenaufruf");
            localDepth++;
            try{return LocalMethod(methodName);}finally{localDepth--;}
        }
        if(reply.TryGetProperty("arguments",out var updated))
            LoadArguments(updated);
        return reply.GetProperty("success").GetBoolean();
    }
    private bool Run(string identity,bool immediately,bool byId)
    {
        var reply=Rpc("run",identity,args,immediately,byId);
        if(reply.TryGetProperty("arguments",out var updated))
            LoadArguments(updated);
        return reply.GetProperty("success").GetBoolean();
    }
    public bool RunAction(string actionName,bool runImmediately=true)=>Run(actionName,runImmediately,false);
    public bool RunActionById(string actionId,bool runImmediately=true)=>Run(actionId,runImmediately,true);
}

public static class SorgobotHost
{
    private static bool InvokeBool(CPHInline script,string method)
    {
        var target=typeof(CPHInline).GetMethod(method,BindingFlags.Public|BindingFlags.Instance,null,Type.EmptyTypes,null);
        if(target==null || target.ReturnType!=typeof(bool))throw new Exception("Expected a public parameterless bool method: "+method);
        try{return (bool)target.Invoke(script,null)!;}
        catch(TargetInvocationException error){throw error.InnerException ?? error;}
    }
    private static MethodInfo? Lifecycle(string name)
    {
        var methods=typeof(CPHInline).GetMethods(BindingFlags.Public|BindingFlags.Instance|BindingFlags.Static);
        var named=Array.FindAll(methods,m=>m.Name==name);
        if(named.Length==0)return null;
        if(named.Length!=1 || named[0].IsStatic || named[0].ReturnType!=typeof(void) || named[0].GetParameters().Length!=0 || named[0].IsDefined(typeof(System.Runtime.CompilerServices.AsyncStateMachineAttribute),false))
            throw new Exception("Lifecycle requires synchronous public void "+name+"() without parameters");
        return named[0];
    }
    public static int Main()
    {
        var protocol=Console.Out;var input=Console.In;
        Console.SetOut(Console.Error);
        CPHInline? script=null;
        bool initialized=false;
        bool disposed=false;
        while(true)
        {
            string? line=input.ReadLine();
            if(line==null)return 0;
            string operation="";
            try
            {
                using var request=JsonDocument.Parse(line);
                var root=request.RootElement;
                operation=root.GetProperty("operation").GetString()!;
                if(operation=="init")
                {
                    if(script!=null)throw new Exception("Code already initialized");
                    var init=Lifecycle("Init");Lifecycle("Dispose");
                    script=new CPHInline();
                    script.CPH=new SorgobotCPH(protocol,input,root.GetProperty("arguments"),root.GetProperty("codeId").GetString()!);
                    script.CPH.LocalMethod=method=>InvokeBool(script,method);
                    init?.Invoke(script,null);
                    initialized=true;
                    protocol.WriteLine(JsonSerializer.Serialize(new {type="ready"}));
                }
                else if(operation=="invoke")
                {
                    if(!initialized || disposed || script==null)throw new Exception("Code is not initialized");
                    script.CPH.args.Clear();
                    script.CPH.LoadArguments(root.GetProperty("arguments"));
                    string method=root.GetProperty("method").GetString()!;
                    bool result=InvokeBool(script,method);
                    protocol.WriteLine(JsonSerializer.Serialize(new {type="done",result,arguments=script.CPH.args}));
                }
                else if(operation=="dispose")
                {
                    if(script!=null && !disposed)
                    {
                        disposed=true;
                        script.CPH.args.Clear();
                        Lifecycle("Dispose")?.Invoke(script,null);
                    }
                    protocol.WriteLine(JsonSerializer.Serialize(new {type="disposed"}));protocol.Flush();return 0;
                }
                else throw new Exception("Unknown script operation");
            }
            catch(Exception error)
            {
                var cause=error is TargetInvocationException invocation ? invocation.InnerException ?? error : error;
                protocol.WriteLine(JsonSerializer.Serialize(new {type="error",error=cause.Message}));
                if(operation=="dispose"){protocol.Flush();return 1;}
            }
            protocol.Flush();
        }
    }
}

namespace Streamer.bot.Plugin.Interface.Model
{
    public class ActionData
    {
        public Guid Id { get; set; }
        public string Name { get; set; } = "";
        public bool Enabled { get; set; }
        public string Group { get; set; } = "";
        public string Queue { get; set; } = "";
        public Guid QueueId { get; set; }
    }
}

public class NativeValueConverter : JsonConverter<object>
{
    public override object? Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
    {
        using var document=JsonDocument.ParseValue(ref reader);
        return ConvertValue(document.RootElement);
    }
    private static object? ConvertValue(JsonElement value)
    {
        switch(value.ValueKind)
        {
            case JsonValueKind.Null: return null;
            case JsonValueKind.True: return true;
            case JsonValueKind.False: return false;
            case JsonValueKind.String: return value.GetString();
            case JsonValueKind.Number:
                if(value.TryGetInt32(out var integer))return integer;
                if(value.TryGetInt64(out var longInteger))return longInteger;
                return value.GetDouble();
            case JsonValueKind.Array:
                var list=new List<object?>();foreach(var child in value.EnumerateArray())list.Add(ConvertValue(child));return list;
            case JsonValueKind.Object:
                var dictionary=new Dictionary<string,object?>();foreach(var child in value.EnumerateObject())dictionary[child.Name]=ConvertValue(child.Value);return dictionary;
            default: throw new JsonException("Unsupported native value");
        }
    }
    public override void Write(Utf8JsonWriter writer, object value, JsonSerializerOptions options)
    {
        if(value.GetType()==typeof(object)){writer.WriteStartObject();writer.WriteEndObject();}
        else JsonSerializer.Serialize(writer,value,value.GetType(),options);
    }
}

namespace Streamer.bot.Plugin.Interface.Model
{
    public class GlobalVariableValue
    {
        public string VariableName { get; set; } = "";
        public object? Value { get; set; }
        public DateTime LastWrite { get; set; }
        public bool LastWriteKnown { get; set; }
    }
    public class UserVariableValue<T>
    {
        public string UserId { get; set; } = "";
        public string UserLogin { get; set; } = "";
        public string UserName { get; set; } = "";
        public string UserType { get; set; } = "";
        public string VariableName { get; set; } = "";
        public T Value { get; set; } = default!;
        public DateTime LastWrite { get; set; }
        public bool LastWriteKnown { get; set; }
        public bool UserInfoAvailable { get; set; }
    }
}

namespace Streamer.bot.Plugin.Interface.Enums
{
    public enum Platform { Twitch=0, YouTube=1, Kick=2 }
}
namespace Streamer.bot.Plugin.Interface.Model
{
    public class CommandData
    {
        public Guid Id { get; set; }
        public string Name { get; set; } = "";
        public bool Enabled { get; set; }
        public string Group { get; set; } = "";
        public int Mode { get; set; }
        public List<string> Commands { get; set; } = new();
        public string RegexCommand { get; set; } = "";
        public bool CaseSensitive { get; set; }
        public List<string> Sources { get; set; } = new();
    }
    public class CommandCounter
    {
        public string UserId { get; set; } = "";
        public string UserLogin { get; set; } = "";
        public string UserName { get; set; } = "";
        public string Platform { get; set; } = "";
        public int Count { get; set; }
        public int Source { get; set; }
        public DateTime LastUsed { get; set; }
        public bool LastUsedKnown { get; set; }
        public bool UserInfoAvailable { get; set; }
        public int LegacyUnassignedCount { get; set; }
    }
}

namespace Streamer.bot.Plugin.Interface.Model
{
    public class GroupUser
    {
        public string Id { get; set; } = "";
        public string Type { get; set; } = "";
        public string Login { get; set; } = "";
        public string Username { get; set; } = "";
        public bool UserInfoAvailable { get; set; }
    }
}

namespace Streamer.bot.Common.Events
{
    public enum EventSource
    {
        General = 0,
        Twitch = 100,
        Streamlabs = 200,
        StreamElements = 1200,
        SpeechToText = 300,
        Command = 400,
        FileWatcher = 500,
        FileTail = 510,
        Quote = 600,
        Misc = 700,
        Raw = 800,
        WebsocketClient = 900,
        WebsocketCustomServer = 2000,
        DonorDrive = 3000,
        YouTube = 4000,
        Pulsoid = 5000,
        HypeRate = 6000,
        Kofi = 7000,
        Patreon = 8000,
        Application = 9000,
        TipeeeStream = 10000,
        TreatStream = 11000,
        Shopify = 13000,
        Obs = 14000,
        Midi = 15000,
        Inputs = 16000,
        StreamDeck = 17000,
        Custom = 18000,
        VTubeStudio = 19000,
        CrowdControl = 20000,
        Elgato = 21000,
        StreamlabsDesktop = 22000,
        SpeakerBot = 23000,
        Fourthwall = 24000,
        ThrowingSystem = 27000,
        Pallygg = 28000,
        StreamerBotRemote = 29000,
        StreamerBot = 34000,
        VoiceMod = 30000,
        Group = 32000,
        MeldStudio = 33000,
        Kick = 35000,
        StreamLoots = 36000,
        Throne = 37000,
        System = 42000,
        Invalid = 2147483647,
    }
    public enum EventType
    {
        TwitchFollow = 101,
        TwitchCheer = 102,
        TwitchSub = 103,
        TwitchReSub = 104,
        TwitchGiftSub = 105,
        TwitchGiftBomb = 106,
        TwitchRaid = 107,
        TwitchHypeTrainStart = 108,
        TwitchHypeTrainUpdate = 109,
        TwitchHypeTrainLevelUp = 110,
        TwitchHypeTrainEnd = 111,
        TwitchRewardRedemption = 112,
        TwitchRewardCreated = 113,
        TwitchRewardUpdated = 114,
        TwitchRewardDeleted = 115,
        TwitchAutomaticRewardRedemption = 194,
        TwitchPowerUpRedemption = 196,
        TwitchCommunityGoalContribution = 116,
        TwitchCommunityGoalEnded = 117,
        TwitchStreamUpdate = 118,
        TwitchWhisper = 119,
        TwitchFirstWord = 120,
        TwitchSubCounterRollover = 121,
        TwitchStreamUpdateGameOnConnect = 123,
        TwitchPresentViewers = 124,
        TwitchPollCreated = 125,
        TwitchPollUpdated = 126,
        TwitchPollCompleted = 127,
        TwitchPollTerminated = 161,
        TwitchPollArchived = 473,
        TwitchPredictionCreated = 128,
        TwitchPredictionUpdated = 129,
        TwitchPredictionCompleted = 130,
        TwitchPredictionCanceled = 131,
        TwitchPredictionLocked = 132,
        TwitchChatMessage = 133,
        TwitchChatMessageDeleted = 135,
        TwitchUserTimedOut = 136,
        TwitchUserBanned = 137,
        TwitchUserUnbanned = 191,
        TwitchAnnouncement = 138,
        TwitchAdRun = 139,
        TwitchBotWhisper = 140,
        TwitchCharityDonation = 141,
        TwitchCharityCompleted = 142,
        TwitchCoinCheer = 143,
        TwitchShoutoutCreated = 144,
        TwitchShoutoutReceived = 156,
        TwitchUserUntimedOut = 145,
        TwitchCharityStarted = 146,
        TwitchCharityProgress = 147,
        TwitchGoalBegin = 148,
        TwitchGoalProgress = 149,
        TwitchGoalEnd = 150,
        TwitchShieldModeBegin = 151,
        TwitchShieldModeEnd = 152,
        TwitchStreamOnline = 154,
        TwitchStreamOffline = 155,
        TwitchChatCleared = 157,
        TwitchRaidStart = 158,
        TwitchRaidSend = 159,
        TwitchRaidCancelled = 160,
        TwitchPyramidSuccess = 162,
        TwitchPyramidBroken = 163,
        TwitchViewerCountUpdate = 164,
        TwitchGuestStarSessionBegin = 165,
        TwitchGuestStarSessionEnd = 166,
        TwitchGuestStarGuestUpdate = 167,
        TwitchGuestStarSlotUpdate = 168,
        TwitchGuestStarSettingsUpdate = 169,
        TwitchHypeChat = 170,
        TwitchHypeChatLevel = 172,
        TwitchRewardRedemptionUpdated = 171,
        TwitchBroadcasterAuthenticated = 173,
        TwitchBroadcasterChatConnected = 174,
        TwitchBroadcasterChatDisconnected = 175,
        TwitchBroadcasterEventSubConnected = 178,
        TwitchBroadcasterEventSubDisconnected = 179,
        TwitchBotEventSubConnected = 184,
        TwitchBotEventSubDisconnected = 185,
        TwitchSevenTVEmoteAdded = 180,
        TwitchSevenTVEmoteRemoved = 181,
        TwitchBetterTTVEmoteAdded = 182,
        TwitchBetterTTVEmoteRemoved = 183,
        TwitchUpcomingAd = 186,
        TwitchModeratorAdded = 187,
        TwitchModeratorRemoved = 188,
        TwitchVipAdded = 189,
        TwitchVipRemoved = 190,
        TwitchUnbanRequestApproved = 192,
        TwitchUnbanRequestDenied = 193,
        TwitchUnbanRequestCreated = 195,
        TwitchBlockedTermsAdded = 465,
        TwitchBlockedTermsDeleted = 466,
        TwitchPermittedTermsAdded = 469,
        TwitchPermittedTermsDeleted = 470,
        TwitchChatEmoteModeOn = 451,
        TwitchChatEmoteModeOff = 452,
        TwitchChatFollowerModeOn = 453,
        TwitchChatFollowerModeOff = 454,
        TwitchChatFollowerModeChanged = 455,
        TwitchChatSlowModeOn = 456,
        TwitchChatSlowModeOff = 457,
        TwitchChatSlowModeChanged = 458,
        TwitchChatSubscriberModeOn = 459,
        TwitchChatSubscriberModeOff = 460,
        TwitchChatUniqueModeOn = 461,
        TwitchChatUniqueModeOff = 462,
        TwitchAutoModMessageHeld = 463,
        TwitchAutoModMessageUpdate = 464,
        TwitchWarnedUser = 467,
        TwitchWarningAcknowledged = 471,
        TwitchSuspiciousUserMessage = 495,
        TwitchSuspiciousUserUpdate = 468,
        TwitchWatchStreak = 472,
        TwitchModiversary = 497,
        TwitchSharedChatSessionBegin = 474,
        TwitchSharedChatSessionUpdate = 475,
        TwitchSharedChatSessionEnd = 476,
        TwitchPrimePaidUpgrade = 477,
        TwitchPayItForward = 478,
        TwitchGiftPaidUpgrade = 479,
        TwitchBitsBadgeTier = 480,
        TwitchSharedChatAnnouncement = 481,
        TwitchSharedChatRaid = 482,
        TwitchSharedChatPrimePaidUpgrade = 483,
        TwitchSharedChatGiftPaidUpgrade = 484,
        TwitchSharedChatPayItForward = 485,
        TwitchSharedChatSub = 486,
        TwitchSharedChatResub = 487,
        TwitchSharedChatSubGift = 488,
        TwitchSharedChatCommunitySubGift = 489,
        TwitchSharedChatUserBanned = 490,
        TwitchSharedChatUserUnbanned = 491,
        TwitchSharedChatUserTimedout = 492,
        TwitchSharedChatUserUntimedout = 493,
        TwitchSharedChatMessageDeleted = 494,
        TwitchSharedModiversary = 498,
        TwitchCustomPowerUpRedemption = 496,
        StreamlabsDonation = 201,
        StreamlabsMerchandise = 202,
        StreamlabsConnected = 203,
        StreamlabsDisconnected = 204,
        StreamlabsCharityDonation = 205,
        StreamlabsAuthenticated = 206,
        CommandTriggered = 401,
        CommandCooldown = 402,
        SpeechToTextDictation = 301,
        SpeechToTextCommand = 302,
        FileWatcherChanged = 501,
        FileWatcherCreated = 502,
        FileWatcherDeleted = 503,
        FileWatcherRenamed = 504,
        FileTailChanged = 511,
        QuoteAdded = 601,
        QuoteShow = 602,
        TimedAction = 701,
        Test = 702,
        ProcessStarted = 703,
        ProcessStopped = 704,
        ChatWindowAction = 705,
        StreamerbotStarted = 706,
        StreamerbotExiting = 707,
        ToastActivation = 708,
        GlobalVariableUpdated = 709,
        UserGlobalVariableUpdated = 710,
        GlobalVariableCreated = 711,
        GlobalVariableDeleted = 712,
        Custom = 1,
        RawAction = 801,
        RawSubAction = 802,
        RawActionCompleted = 806,
        WebsocketClientOpen = 803,
        WebsocketClientClose = 804,
        WebsocketClientMessage = 805,
        StreamElementsTip = 1201,
        StreamElementsMerch = 1202,
        StreamElementsConnected = 1203,
        StreamElementsDisconnected = 1204,
        StreamElementsAuthenticated = 1205,
        WebsocketCustomServerOpen = 2001,
        WebsocketCustomServerClose = 2002,
        WebsocketCustomServerMessage = 2003,
        DonorDriveDonation = 3001,
        DonorDriveProfileUpdated = 3002,
        DonorDriveIncentive = 3003,
        YouTubeBroadcastStarted = 4001,
        YouTubeBroadcastEnded = 4002,
        YouTubeMessage = 4003,
        YouTubeMessageDeleted = 4004,
        YouTubeUserBanned = 4005,
        YouTubeSuperChat = 4006,
        YouTubeSuperSticker = 4007,
        YouTubeNewSponsor = 4008,
        YouTubeMemberMileStone = 4009,
        YouTubeNewSponsorOnlyStarted = 4010,
        YouTubeNewSponsorOnlyEnded = 4011,
        YouTubeStatisticsUpdated = 4012,
        YouTubeBroadcastUpdated = 4013,
        YouTubeMembershipGift = 4014,
        YouTubeGiftMembershipReceived = 4015,
        YouTubeFirstWords = 4016,
        YouTubePresentViewers = 4017,
        YouTubeNewSubscriber = 4018,
        YouTubeBroadcastMonitoringStarted = 4019,
        YouTubeBroadcastMonitoringEnded = 4020,
        YouTubeBroadcastAdded = 4021,
        YouTubeBroadcastRemoved = 4022,
        YouTubePollClosed = 4027,
        YouTubePollStarted = 4028,
        YouTubePollUpdated = 4029,
        YouTubeJewelsGifted = 4030,
        YouTubeUserTimedout = 4031,
        YouTubeSevenTVEmoteAdded = 4023,
        YouTubeSevenTVEmoteRemoved = 4024,
        YouTubeBetterTTVEmoteAdded = 4025,
        YouTubeBetterTTVEmoteRemoved = 4026,
        PulsoidHeartRatePulse = 5001,
        HypeRateHeartRatePulse = 6001,
        HypeRateTwitchClipCreated = 6002,
        HypeRateConnected = 6003,
        HypeRateDisconnected = 6004,
        KofiDonation = 7001,
        KofiSubscription = 7002,
        KofiResubscription = 7003,
        KofiShopOrder = 7004,
        KofiCommission = 7005,
        PatreonFollowCreated = 8001,
        PatreonFollowDeleted = 8002,
        PatreonPledgeCreated = 8003,
        PatreonPledgeUpdated = 8004,
        PatreonPledgeDeleted = 8005,
        ApplicationActionAdded = 9001,
        ApplicationActionUpdated = 9002,
        ApplicationActionDeleted = 9003,
        ApplicationImport = 9004,
        ApplicationCommandAdded = 9005,
        ApplicationCommandUpdated = 9006,
        ApplicationCommandDeleted = 9007,
        GroupAdded = 32001,
        GroupRemoved = 32002,
        GroupCleared = 32003,
        GroupUsersAdded = 32004,
        GroupUsersRemoved = 32005,
        TipeeeStreamDonation = 10001,
        TreatStreamTreat = 11001,
        TreatStreamAuthenticated = 11002,
        TreatStreamConnected = 11003,
        TreatStreamDisconnected = 11004,
        ShopifyOrderCreated = 13001,
        ShopifyOrderPaid = 13002,
        ObsConnected = 14001,
        ObsDisconnected = 14002,
        ObsEvent = 14003,
        ObsSceneChanged = 14004,
        ObsStreamingStarted = 14005,
        ObsStreamingStopped = 14006,
        ObsRecordingStarted = 14007,
        ObsRecordingStopped = 14008,
        ObsVendorEvent = 14009,
        MidiMessage = 15001,
        InputKeyPress = 16001,
        InputMouseClick = 16002,
        StreamDeckAction = 17001,
        StreamDeckConnected = 17002,
        StreamDeckDisconnected = 17003,
        StreamDeckInfo = 17004,
        CustomEvent = 18001,
        CustomCodeEvent = 18002,
        VTubeStudioModelLoaded = 19001,
        VTubeStudioModelUnloaded = 19002,
        VTubeStudioBackgroundChanged = 19003,
        VTubeStudioModelConfigChanged = 19004,
        VTubeStudioHotkeyTriggered = 19005,
        VTubeStudioModelAnimation = 19006,
        VTubeStudioConnected = 19007,
        VTubeStudioDisconnected = 19008,
        VTubeStudioTrackingStatusChanged = 19009,
        VTubeStudioItemEvent = 19010,
        VTubeStudioModelClicked = 19011,
        CrowdControlGameSessionStart = 20001,
        CrowdControlGameSessionEnd = 20002,
        CrowdControlEffectRequest = 20003,
        CrowdControlEffectSuccess = 20004,
        CrowdControlEffectFailure = 20005,
        CrowdControlTimedEffectStarted = 20006,
        CrowdControlTimedEffectEnded = 20007,
        CrowdControlTimedEffectUpdated = 20008,
        CrowdControlCoinExchange = 20009,
        ElgatoWaveLinkOutputSwitched = 21001,
        ElgatoWaveLinkOutputVolumeChanged = 21002,
        ElgatoWaveLinkOutputMuteChanged = 21003,
        ElgatoWaveLinkSelectedOutputChanged = 21004,
        ElgatoWaveLinkInputVolumeChanged = 21005,
        ElgatoWaveLinkInputMuteChanged = 21006,
        ElgatoWaveLinkInputNameChanged = 21007,
        ElgatoWaveLinkMicrophoneGainChanged = 21008,
        ElgatoWaveLinkMicrophoneOutputVolumeChanged = 21009,
        ElgatoWaveLinkMicrophoneBalanceChanged = 21010,
        ElgatoWaveLinkMicrophoneMuteChanged = 21011,
        ElgatoWaveLinkMicrophoneSettingChanged = 21012,
        ElgatoWaveLinkFilterAdded = 21013,
        ElgatoWaveLinkFilterChanged = 21014,
        ElgatoWaveLinkFilterDeleted = 21015,
        ElgatoWaveLinkFilterBypassStateChanged = 21016,
        ElgatoWaveLinkConnected = 21017,
        ElgatoWaveLinkDisconnected = 21018,
        ElgatoWaveLinkInputLevelMeterChanged = 21019,
        ElgatoWaveLinkOutputLevelMeterChanged = 21020,
        ElgatoCameraHubConnected = 21301,
        ElgatoCameraHubDisconnected = 21302,
        ElgatoCameraHubWebcamConnected = 21341,
        ElgatoCameraHubWebcamrDisconnected = 21342,
        ElgatoCameraHubWebcamActivated = 21351,
        ElgatoCameraHubWebcamDeactivated = 21352,
        ElgatoCameraHubSelectedWebcamChanged = 21353,
        ElgatoCameraHubWebcamMirrored = 21354,
        ElgatoCameraHubWebcamFlipped = 21355,
        ElgatoCameraHubWebcamDeviceOrientationChanged = 21356,
        ElgatoCameraHubWebcamExposureAutoLockEnabled = 21357,
        ElgatoCameraHubWebcamExposureAutoLockDisabled = 21358,
        ElgatoCameraHubWebcamSnapshotTaken = 21359,
        ElgatoCameraHubWebcamZoomChanged = 21360,
        ElgatoCameraHubWebcamContrastChanged = 21361,
        ElgatoCameraHubWebcamWhiteBalanceChanged = 21362,
        ElgatoCameraHubWebcamAutoExposureEnabled = 21363,
        ElgatoCameraHubWebcamAutoExposureDisabled = 21364,
        ElgatoCameraHubWebcamAutoWhiteBalanceEnabled = 21365,
        ElgatoCameraHubWebcamAutoWhiteBalanceDisabled = 21366,
        ElgatoCameraHubWebcamNoiseReductionEnabled = 21367,
        ElgatoCameraHubWebcamNoiseReductionDisabled = 21368,
        ElgatoCameraHubWebcamISOChanged = 21369,
        ElgatoCameraHubWebcamShutterSpeedChanged = 21370,
        ElgatoCameraHubWebcamSharpnessChanged = 21371,
        ElgatoCameraHubWebcamAntiFlickerChanged = 21372,
        ElgatoCameraHubWebcamLensChanged = 21373,
        ElgatoCameraHubWebcamARLensChanged = 21374,
        ElgatoCameraHubWebcamBitrateChanged = 21375,
        ElgatoCameraHubWebcamFlashEnabled = 21376,
        ElgatoCameraHubWebcamFlashDisabled = 21377,
        ElgatoCameraHubWebcamPanChanged = 21378,
        ElgatoCameraHubTiltChanged = 21379,
        ElgatoCameraHubWebcamOverscanChanged = 21380,
        ElgatoCameraHubWebcamAutoFocusEnabled = 21381,
        ElgatoCameraHubWebcamAutoFocusDisabled = 21382,
        ElgatoCameraHubWebcamFocusChanged = 21383,
        ElgatoCameraHubWebcamWhiteBalanceTintChanged = 21384,
        ElgatoCameraHubWebcamBrightnessChanged = 21385,
        ElgatoCameraHubWebcamSaturationChanged = 21386,
        ElgatoCameraHubWebcamLiveISOChanged = 21387,
        ElgatoCameraHubWebcamLiveShutterSpeedChanged = 21388,
        ElgatoCameraHubWebcamLiveWhiteBalanceChanged = 21389,
        ElgatoCameraHubWebcamLiveWhiteBalanceTintChanged = 21390,
        ElgatoCameraHubPrompterConnected = 21401,
        ElgatoCameraHubPrompterDisconnected = 21402,
        ElgatoCameraHubPrompterModeChanged = 21403,
        ElgatoCameraHubPrompterBrightnessChanged = 21404,
        ElgatoCameraHubPrompterFontChanged = 21405,
        ElgatoCameraHubPrompterFontSizeChanged = 21406,
        ElgatoCameraHubPrompterAutoScrollEnabled = 21407,
        ElgatoCameraHubPrompterAutoScrollDisabled = 21408,
        ElgatoCameraHubPrompterAutoScrollChapterEnabled = 21409,
        ElgatoCameraHubPrompterAutoScrollChapterDisabled = 21410,
        ElgatoCameraHubPrompterScrollSpeedChanged = 21411,
        ElgatoCameraHubPrompterOpacityChanged = 21412,
        ElgatoCameraHubPrompterHorizontalMarginChanged = 21413,
        ElgatoCameraHubPrompterVerticalMarginChanged = 21414,
        ElgatoCameraHubPrompterLineSpacingChanged = 21415,
        ElgatoCameraHubPrompterFontColorChanged = 21416,
        ElgatoCameraHubPrompterBackgroundColorChanged = 21417,
        ElgatoCameraHubPrompterSelectedChapterChanged = 21418,
        ElgatoCameraHubPrompterChannelsChanged = 21419,
        ElgatoCameraHubPrompterSelectedChannelChanged = 21420,
        ElgatoCameraHubPrompterContrastChanged = 21421,
        ElgatoCameraHubPrompterCrosshairEnabled = 21422,
        ElgatoCameraHubPrompterCrosshairDisabled = 21423,
        ElgatoCameraHubPrompterCrosshairImageChanged = 21424,
        ElgatoCameraHubPrompterCrosshairColorChanged = 21425,
        ElgatoCameraHubPrompterSelectedScriptChanged = 21426,
        ElgatoStreamDeckMcpConnected = 21501,
        ElgatoStreamDeckMcpDisconnected = 21502,
        StreamlabsDesktopConnected = 22001,
        StreamlabsDesktopDisconnected = 22002,
        StreamlabsDesktopSceneChanged = 22003,
        StreamlabsDesktopStreamingStarted = 22004,
        StreamlabsDesktopStreamingStopped = 22005,
        StreamlabsDesktopRecordingStarted = 22006,
        StreamlabsDesktopRecordingStopped = 22007,
        SpeakerBotConnected = 23001,
        SpeakerBotDisconnected = 23002,
        FourthwallProductCreated = 24001,
        FourthwallProductUpdated = 24002,
        FourthwallGiftPurchase = 24003,
        FourthwallOrderPlaced = 24004,
        FourthwallOrderUpdated = 24005,
        FourthwallDonation = 24006,
        FourthwallSubscriptionPurchased = 24007,
        FourthwallSubscriptionExpired = 24008,
        FourthwallSubscriptionChanged = 24009,
        FourthwallThankYouSent = 24010,
        FourthwallNewsletterSubscribed = 24011,
        FourthwallGiftDrawStarted = 24012,
        FourthwallGiftDrawEnded = 24013,
        ThrowingSystemConnected = 27001,
        ThrowingSystemWebsocketConnected = 27002,
        ThrowingSystemWebsocketDisconnected = 27003,
        ThrowingSystemEventsConnected = 27004,
        ThrowingSystemEventsDisconnected = 27005,
        ThrowingSystemItemHit = 27010,
        ThrowingSystemTriggerActivated = 27011,
        ThrowingSystemTriggerEnded = 27012,
        PallyggConnected = 28001,
        PallyggDisconnected = 28002,
        PallyggCampaignTip = 28003,
        StreamerBotRemoteInstanceConnected = 29001,
        StreamerBotRemoteInstanceDisconnected = 29002,
        StreamerBotRemoteInstanceTrigger = 29003,
        StreamerBotRemoteInstanceSignal = 29004,
        StreamerBotCustomWebook = 34001,
        VoiceModConnected = 30001,
        VoiceModDisconnected = 30002,
        VoiceModVoiceLoaded = 30003,
        VoiceModSoundboardChanged = 30004,
        MeldStudioConnected = 33001,
        MeldStudioDisconnected = 33002,
        MeldStudioStreamingStarted = 33003,
        MeldStudioStreamingStopped = 33004,
        MeldStudioRecordingStarted = 33005,
        MeldStudioRecordingStopped = 33006,
        MeldStudioSceneChanged = 33007,
        MeldStudioLayerVisbilityChanged = 33008,
        MeldStudioLEffectEnabledStateChanged = 33009,
        MeldStudioTrackMonitoringStateChanged = 33010,
        MeldStudioTrackMustedStateChanged = 33011,
        MeldStudioEvent = 33012,
        KickBroadcasterAuthenticated = 35001,
        KickBroadcasterChatConnected = 35002,
        KickBroadcasterChatDisconnected = 35003,
        KickFirstWords = 35008,
        KickPresentViewers = 35009,
        KickChatMessage = 35010,
        KickFollow = 35011,
        KickStreamOnline = 35012,
        KickStreamOffline = 35013,
        KickSubscription = 35014,
        KickResubscription = 35015,
        KickGiftSubscription = 35016,
        KickMassGiftSubscription = 35017,
        KickUserTimedOut = 35018,
        KickUserBanned = 35019,
        KickChannelUpdate = 35020,
        KickSevenTVEmoteAdded = 35021,
        KickSevenTVEmoteRemoved = 35022,
        KickViewerCountUpdate = 35023,
        KickRewardRedemption = 35024,
        KickKicksGifted = 35025,
        StreamLootsPackPurchased = 36001,
        StreamLootsPackGifted = 36002,
        StreamLootsCardRedeemed = 36003,
        StreamLootsReaction = 36004,
        ThroneGiftPurchased = 37001,
        ThroneContributionPurchased = 37002,
        ThroneGiftCrowdfunded = 37003,
        SystemClipboardChanged = 42001,
    }
}

// Dedicated CPH parser: keep typed .NET values and never execute generated replacement text.
internal sealed class CphTextParser
{
    private readonly Dictionary<string,object?> values=new(StringComparer.OrdinalIgnoreCase);
    private readonly Func<bool,Dictionary<string,object?>> globals;
    private readonly DateTime now=DateTime.Now;
    private readonly Func<string,string?,string> math;
    internal CphTextParser(Dictionary<string,object?> arguments,Func<bool,Dictionary<string,object?>> globals,Func<string,string?,string> math)
    {
        this.globals=globals;this.math=math;
        foreach(var pair in arguments)values[pair.Key]=pair.Value is JsonElement json ? json.Deserialize<object>(new JsonSerializerOptions {Converters={new NativeValueConverter()}}) : pair.Value;
        // The original's generic entries are defaults; explicit action arguments take precedence.
        values.TryAdd("date",now);values.TryAdd("time",now);values.TryAdd("longtime",now);
        values.TryAdd("filedatetime",now);values.TryAdd("unixtime",new DateTimeOffset(now).ToUnixTimeSeconds());
        values.TryAdd("lf","\r\n");
    }
    private static string Format(object? value,string? format)=>value is IFormattable typed ? typed.ToString(format,System.Globalization.CultureInfo.CurrentCulture) ?? "" : value?.ToString() ?? "";
    internal string Render(string text,bool functions=true,bool formats=true,int depth=0)
    {
        if(string.IsNullOrEmpty(text))return text;
        if(depth>32)throw new FormatException("CPH.Parse inline nesting exceeds 32 levels");
        var output=new System.Text.StringBuilder();
        for(int i=0;i<text.Length;)
        {
            char marker=text[i];
            if("%~@${".Contains(marker) && i+1<text.Length && text[i+1]==marker){output.Append(marker);i+=2;continue;}
            if(functions && marker=='$')
            {
                int nameEnd=i+1;while(nameEnd<text.Length && (char.IsLetterOrDigit(text[nameEnd]) || text[nameEnd]=='_'))nameEnd++;
                if(nameEnd<text.Length && text[nameEnd]=='(' && nameEnd>i+1)
                {
                    int end=nameEnd+1,balance=1;
                    for(;end<text.Length && balance>0;end++){if(text[end]=='(')balance++;else if(text[end]==')')balance--;}
                    int tokenEnd=end;string? inlineFormat=null;
                    if(balance==0 && end<text.Length && text[end]==':') {
                        int stop=text.IndexOf('$',end+1);if(stop>=0){inlineFormat=text[(end+1)..stop];tokenEnd=stop;}
                    }
                    if(balance==0 && tokenEnd<text.Length && text[tokenEnd]=='$')
                    {
                        string name=text[(i+1)..nameEnd].ToLowerInvariant(), body=text[(nameEnd+1)..(end-1)];
                        string result;
                        if(name=="parse") {
                            string key=Render(body,false,false,depth+1);
                            result=values.TryGetValue(key,out var value)?Format(value,null):"%"+key+"%";
                        }
                        else if(name=="length")result=Format(Render(body,true,true,depth+1).Length,inlineFormat);
                        else if(name=="math")result=math(Render(body,true,true,depth+1),inlineFormat);
                        else result=Render(body,true,true,depth+1);
                        output.Append(result);i=tokenEnd+1;continue;
                    }
                }
            }
            if(marker=='%' || marker=='~' || marker=='@')
            {
                int end=text.IndexOf(marker,i+1);
                if(end>i+1)
                {
                    string token=text[(i+1)..end],key=token;string? format=null;
                    int colon=token.IndexOf(':');
                    if(formats && colon>=0){key=token[..colon];format=token[(colon+1)..];}
                    var source=marker=='%'?values:globals(marker=='~');
                    if(source.TryGetValue(key,out var value)) {
                        if(format==null && marker=='%' && value is DateTime)format=key.ToLowerInvariant() switch {"date"=>"yyyy/MM/dd","time"=>"hh:mm","longtime"=>"hh:mm:ss","filedatetime"=>"yyyyMMdd.hhmmss",_=>null};
                        output.Append(Format(value,format));
                    }
                    else output.Append(text,i,end-i+1);
                    i=end+1;continue;
                }
            }
            output.Append(marker);i++;
        }
        return output.ToString();
    }
}

namespace Streamer.bot.Plugin.Interface.Model
{
    public class QuoteData
    {
        public DateTime Timestamp { get; set; }
        public int Id { get; set; }
        public string UserId { get; set; } = null!;
        public string User { get; set; } = null!;
        public string Platform { get; set; } = null!;
        public string GameName { get; set; } = null!;
        public string Quote { get; set; } = null!;
    }
}

// Original 1.0.7 public model names/properties; native JSON values populate these DTOs.
namespace Streamer.bot.Plugin.Interface.Model
{
    public class TwitchUserInfo : global::Streamer.bot.Plugin.Interface.Model.BaseUserInfo
    {
        public bool IsSubscribed { get; set; } = default!;
        public string SubscriptionTier { get; set; } = default!;
        public bool IsModerator { get; set; } = default!;
        public bool IsVip { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface.Model
{
    public class TwitchUserInfoEx : global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo
    {
        public string Description { get; set; } = default!;
        public string ProfileImageUrl { get; set; } = default!;
        public string UserType { get; set; } = default!;
        public bool IsPartner { get; set; } = default!;
        public bool IsAffiliate { get; set; } = default!;
        public bool IsFollowing { get; set; } = default!;
        public DateTime CreatedAt { get; set; } = default!;
        public double AccountAge { get; set; } = default!;
        public string Game { get; set; } = default!;
        public string GameId { get; set; } = default!;
        public string ChannelTitle { get; set; } = default!;
        public global::System.Collections.Generic.List<string> Tags { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface.Model
{
    public class PinnedMessageData
    {
        public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo Sender { get; set; } = default!;
        public global::Streamer.bot.Plugin.Interface.Model.TwitchUserInfo PinnedBy { get; set; } = default!;
        public string MessageId { get; set; } = default!;
        public global::System.Collections.Generic.List<global::Streamer.bot.Plugin.Interface.Model.Twitch.TwitchMessagePartBase> Fragments { get; set; } = default!;
        public DateTime? StartsAt { get; set; } = default!;
        public DateTime? EndsAt { get; set; } = default!;
        public DateTime? UpdatedAt { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class ClipData
    {
        public string Id { get; set; } = default!;
        public string Url { get; set; } = default!;
        public string EmbedUrl { get; set; } = default!;
        public string BroadcasterId { get; set; } = default!;
        public string BroadcasterName { get; set; } = default!;
        public int CreatorId { get; set; } = default!;
        public string CreatorName { get; set; } = default!;
        public string VideoId { get; set; } = default!;
        public string GameId { get; set; } = default!;
        public string Language { get; set; } = default!;
        public string Title { get; set; } = default!;
        public int ViewCount { get; set; } = default!;
        public DateTime CreatedAt { get; set; } = default!;
        public string ThumbnailUrl { get; set; } = default!;
        public float Duration { get; set; } = default!;
        public bool IsFeatured { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class TeamInfo
    {
        public string Id { get; set; } = default!;
        public string Login { get; set; } = default!;
        public string Name { get; set; } = default!;
        public string BackgroundImageUrl { get; set; } = default!;
        public string Banner { get; set; } = default!;
        public string CreatedAt { get; set; } = default!;
        public string UpdatedAt { get; set; } = default!;
        public string Info { get; set; } = default!;
        public string ThumbnailUrl { get; set; } = default!;
        public string TeamName { get; set; } = default!;
        public string TeamDisplayName { get; set; } = default!;
        public string TeamId { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class Cheermote
    {
        public string Prefix { get; set; } = default!;
        public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.CheermoteTier> Tiers { get; set; } = default!;
        public string Type { get; set; } = default!;
        public int Order { get; set; } = default!;
        public DateTime LastUpdated { get; set; } = default!;
        public bool IsCharitable { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface
{
    public class GameInfo
    {
        public string Id { get; set; } = default!;
        public string Name { get; set; } = default!;
        public string BoxArtUrl { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class ClipDownloadData
    {
        public string ClipId { get; set; } = default!;
        public string LandscapeDownloadUrl { get; set; } = default!;
        public string PortraitDownloadUrl { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class StreamMarker
    {
        public string Id { get; set; } = default!;
        public DateTime CreatedAt { get; set; } = default!;
        public string Description { get; set; } = default!;
        public int Position { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface.Enums
{
    public enum TwitchBlockContext
    {
        None = 0,
        Chat = 1,
        Whisper = 2,
    }
}
namespace Streamer.bot.Plugin.Interface.Enums
{
    public enum TwitchBlockReason
    {
        None = 0,
        Harassment = 1,
        Spam = 2,
        Other = 3,
    }
}
namespace Streamer.bot.Plugin.Interface.Model
{
    public class TwitchRewardCounter
    {
        public string UserId { get; set; } = default!;
        public string UserLogin { get; set; } = default!;
        public string UserName { get; set; } = default!;
        public int Count { get; set; } = default!;
        public DateTime LastRedeemed { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface
{
    public class TwitchReward
    {
        public string Id { get; set; } = default!;
        public string Title { get; set; } = default!;
        public string Group { get; set; } = default!;
        public string Prompt { get; set; } = default!;
        public int Cost { get; set; } = default!;
        public bool InputRequired { get; set; } = default!;
        public string BackgroundColor { get; set; } = default!;
        public bool Paused { get; set; } = default!;
        public bool Enabled { get; set; } = default!;
        public bool IsOurs { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class GuestStarSettings
    {
        public bool IsModeratorSendLiveEnabled { get; set; } = default!;
        public int SlotCount { get; set; } = default!;
        public bool IsBrowserSourceAudioEnabled { get; set; } = default!;
        public string GroupLayout { get; set; } = default!;
        public string BrowserSourceToken { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class GuestSession
    {
        public string Id { get; set; } = default!;
        public global::System.Collections.Generic.List<global::Twitch.Common.Models.Api.GuestStar> Guests { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class GuestStarInvite
    {
        public string UserId { get; set; } = default!;
        public DateTime InvitedAt { get; set; } = default!;
        public string Status { get; set; } = default!;
        public bool IsVideoEnabled { get; set; } = default!;
        public bool IsAudioEnabled { get; set; } = default!;
        public bool IsVideoAvailable { get; set; } = default!;
        public bool IsAudioAvailable { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface.Model.Twitch
{
    public class TwitchMessagePartEmote : global::Streamer.bot.Plugin.Interface.Model.Twitch.TwitchMessagePartBase
    {
        public string Source { get; set; } = default!;
        public string ImageUrl { get; set; } = default!;
        public bool ZeroWidth { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface.Model.Twitch
{
    public class TwitchMessagePartMention : global::Streamer.bot.Plugin.Interface.Model.Twitch.TwitchMessagePartBase
    {
        public string UserId { get; set; } = default!;
        public string UserLogin { get; set; } = default!;
        public string UserName { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface.Model.Twitch
{
    public class TwitchMessagePartText : global::Streamer.bot.Plugin.Interface.Model.Twitch.TwitchMessagePartBase
    {
    }
}
namespace Streamer.bot.Plugin.Interface.Model
{
    public class BaseUserInfo
    {
        public string UserName { get; set; } = default!;
        public string UserLogin { get; set; } = default!;
        public string UserId { get; set; } = default!;
        public DateTime LastActive { get; set; } = default!;
        public DateTime PreviousActive { get; set; } = default!;
    }
}
namespace Streamer.bot.Plugin.Interface.Model.Twitch
{
    [System.Text.Json.Serialization.JsonPolymorphic(TypeDiscriminatorPropertyName="$part")]
    [System.Text.Json.Serialization.JsonDerivedType(typeof(global::Streamer.bot.Plugin.Interface.Model.Twitch.TwitchMessagePartText),"text")]
    [System.Text.Json.Serialization.JsonDerivedType(typeof(global::Streamer.bot.Plugin.Interface.Model.Twitch.TwitchMessagePartMention),"mention")]
    [System.Text.Json.Serialization.JsonDerivedType(typeof(global::Streamer.bot.Plugin.Interface.Model.Twitch.TwitchMessagePartEmote),"emote")]
    public class TwitchMessagePartBase
    {
        public string Type { get; set; } = default!;
        public string Text { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class CheermoteTier
    {
        public int MinBits { get; set; } = default!;
        public string Id { get; set; } = default!;
        public string Color { get; set; } = default!;
        public global::Twitch.Common.Models.Api.CheermoteImages Images { get; set; } = default!;
        public bool CanCheer { get; set; } = default!;
        public bool ShowInBitsCard { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class GuestStar
    {
        public string SlotId { get; set; } = default!;
        public bool IsLive { get; set; } = default!;
        public string UserId { get; set; } = default!;
        public string UserName { get; set; } = default!;
        public string UserLogin { get; set; } = default!;
        public int Volume { get; set; } = default!;
        public DateTime AssignedAt { get; set; } = default!;
        public global::Twitch.Common.Models.Api.MediaSettings AudioSettings { get; set; } = default!;
        public global::Twitch.Common.Models.Api.MediaSettings VideoSettings { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class CheermoteImages
    {
        public global::Twitch.Common.Models.Api.CheermoteImage Dark { get; set; } = default!;
        public global::Twitch.Common.Models.Api.CheermoteImage Light { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class MediaSettings
    {
        public bool IsHostEnabled { get; set; } = default!;
        public bool IsGuestEnabled { get; set; } = default!;
        public bool IsAvailable { get; set; } = default!;
    }
}
namespace Twitch.Common.Models.Api
{
    public class CheermoteImage
    {
        public global::System.Collections.Generic.Dictionary<string,string> Animated { get; set; } = default!;
        public global::System.Collections.Generic.Dictionary<string,string> Static { get; set; } = default!;
    }
}

namespace Streamer.bot.Plugin.Interface.Model
{
    public class YouTubeBroadcastInfo
    {
        public DateTime MonitoredAt { get; set; } = default!;
        public string Id { get; set; } = default!;
        public string ChannelId { get; set; } = default!;
        public string LiveChatId { get; set; } = default!;
        public string Title { get; set; } = default!;
        public string Description { get; set; } = default!;
        public string CategoryId { get; set; } = default!;
        public string CategoryName { get; set; } = default!;
        public List<string> Tags { get; set; } = default!;
        public string DefaultLanguage { get; set; } = default!;
        public string DefaultAudioLanguage { get; set; } = default!;
        public string Privacy { get; set; } = default!;
        public DateTime PublishedAt { get; set; } = default!;
        public string Status { get; set; } = default!;
    }
}

namespace Streamer.bot.Plugin.Interface.Model
{
    public class YouTubeUserInfo : BaseUserInfo
    {

    }
}
