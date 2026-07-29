package com.pes.gamingdetector.activities

import androidx.appcompat.app.AppCompatActivity
import com.pes.gamingdetector.util.AuthNavigation
import com.pes.gamingdetector.util.PrefsManager

/**
 * Resume-time auth gate shared by signed-in screens.
 *
 * Activities can remain in Recents after a token expires in the background. Checking
 * here prevents those stale instances from becoming visible or issuing more requests.
 */
abstract class AuthenticatedActivity : AppCompatActivity() {
    /** Call immediately after super.onCreate(), before inflating UI or starting work. */
    protected fun ensureAuthenticatedOnCreate(): Boolean =
        !authenticationRequired() ||
            AuthNavigation.ensureAuthenticated(this, PrefsManager(this))

    final override fun onResume() {
        super.onResume()
        if (authenticationRequired() &&
            !AuthNavigation.ensureAuthenticated(this, PrefsManager(this))) {
            return
        }
        onAuthenticatedResume()
    }

    /** Settings' pre-login endpoint setup is the sole intentionally public variant. */
    protected open fun authenticationRequired(): Boolean = true

    protected open fun onAuthenticatedResume() = Unit
}
