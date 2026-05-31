package com.pes.gamingdetector.util

object Constants {
    // Cloud backend (Render). Override in Settings → Server URL for local dev
    // (e.g. http://127.0.0.1:5000/ with `adb reverse tcp:5000 tcp:5000`).
    const val BASE_URL = "https://gaming-addiction-api.onrender.com/"

    // SharedPreferences keys
    const val PREFS_NAME = "child_app_prefs"
    const val KEY_USER_ID = "user_id"
    const val KEY_USER_NAME = "user_name"
    const val KEY_SERVER_URL = "server_url"
    const val KEY_ACTIVE_SESSION_ID = "active_session_id"
    const val KEY_ACTIVE_SESSION_GAME = "active_session_game"
    const val KEY_ACTIVE_SESSION_PKG = "active_session_pkg"
    const val KEY_ACTIVE_SESSION_START = "active_session_start"
    const val KEY_CHILD_CODE = "child_code"
    const val KEY_AUTH_TOKEN = "auth_token"

    // Notification channels
    const val CHANNEL_MONITORING = "monitoring_channel"
    const val CHANNEL_ALERTS = "alerts_channel"

    // Notification IDs
    const val NOTIF_MONITORING  = 1001
    const val NOTIF_ALERT       = 1002
    const val NOTIF_SESSION_END = 1003

    // Package → display game name (used for auto-session detection + notification capture).
    // Package names verified against Google Play listings; correct a game's package here
    // if it isn't detected (read the foreground package while playing to confirm).
    val PACKAGE_TO_GAME = mapOf(
        // Battle royale / shooters
        "com.tencent.ig"                     to "PUBG Mobile",
        "com.pubg.imobile"                   to "BGMI",
        "com.activision.callofduty.shooter"  to "COD Mobile",
        "com.activision.callofduty.warzone"  to "Warzone Mobile",
        "com.garena.game.freefire"           to "Free Fire",
        "com.dts.freefiremax"                to "Free Fire MAX",
        "com.epicgames.fortnite"             to "Fortnite",
        // MOBA
        "com.mobile.legends"                 to "Mobile Legends",
        "com.tencent.tmgp.sgame"             to "Honor of Kings",
        "com.riotgames.league.wildrift"      to "Wild Rift",
        "com.riotgames.league.valorant"      to "Valorant Mobile",
        // Sandbox / casual / party
        "com.roblox.client"                  to "Roblox",
        "com.mojang.minecraftpe"             to "Minecraft",
        "com.innersloth.spacemafia"          to "Among Us",
        "com.kitkagames.fallbuddies"         to "Stumble Guys",
        "com.supercell.brawlstars"           to "Brawl Stars",
        "com.supercell.clashofclans"         to "Clash of Clans",
        "com.supercell.clashroyale"          to "Clash Royale",
        "com.king.candycrushsaga"            to "Candy Crush",
        "com.kiloo.subwaysurf"               to "Subway Surfers",
        "com.imangi.templerun2"              to "Temple Run 2",
        "com.miniclip.eightballpool"         to "8 Ball Pool",
        // Open world / RPG / racing
        "com.miHoYo.GenshinImpact"           to "Genshin Impact",
        "com.gameloft.android.ANMP.GloftA9HM" to "Asphalt 9",
        "com.nianticlabs.pokemongo"          to "Pokemon Go",
    )

    // Known gaming app packages for UsageStats detection — must match PACKAGE_TO_GAME keys
    val KNOWN_GAMING_PACKAGES = PACKAGE_TO_GAME.keys

    // Timing constants (ms)
    const val VOICE_SEGMENT_DURATION_MS = 10_000L
    const val LIVE_PREDICT_INTERVAL_MS = 60_000L
}
