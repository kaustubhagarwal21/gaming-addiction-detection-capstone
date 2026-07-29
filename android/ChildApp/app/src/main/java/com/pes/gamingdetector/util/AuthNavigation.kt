package com.pes.gamingdetector.util

import android.app.Activity
import android.content.Context
import android.content.Intent
import com.pes.gamingdetector.activities.LoginActivity

object AuthNavigation {
    fun ensureAuthenticated(activity: Activity, prefs: PrefsManager): Boolean {
        if (prefs.isLoggedIn()) return true
        openLogin(activity)
        activity.finish()
        return false
    }

    fun openLogin(context: Context) {
        context.startActivity(Intent(context, LoginActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
        })
    }
}
