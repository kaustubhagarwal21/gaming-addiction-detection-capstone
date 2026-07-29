package com.pes.parentmonitor.activities

import androidx.appcompat.app.AppCompatActivity
import com.pes.parentmonitor.util.AuthNavigation
import com.pes.parentmonitor.util.PrefsManager

/**
 * Auth gate shared by every signed-in screen.
 *
 * Keeping this in a final [onResume] closes the window where an Activity created while
 * authenticated could later be resumed from Recents after logout/token expiry.
 */
abstract class AuthenticatedActivity : AppCompatActivity() {
    final override fun onResume() {
        super.onResume()
        if (!AuthNavigation.ensureAuthenticated(this, PrefsManager(this))) return
        onAuthenticatedResume()
    }

    protected open fun onAuthenticatedResume() = Unit
}
