package com.pes.parentmonitor.util

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Returns an [EncryptedSharedPreferences]-backed store so sensitive values (the auth
 * token, in particular) are encrypted at rest instead of sitting in plaintext XML that
 * any rooted device or backup extraction could read.
 *
 * It implements the same [SharedPreferences] interface, so PrefsManager is otherwise
 * unchanged. On first run it transparently migrates any values from the legacy plaintext
 * store, then wipes it. If the encrypted keyset is ever unreadable (restored backup,
 * keystore reset) it rebuilds the store (worst case: a one-time re-login) and, as a last
 * resort, falls back to plaintext so the app never crashes on launch.
 */
object SecurePrefs {

    fun get(context: Context, plainName: String): SharedPreferences {
        val secureName = plainName + "_secure"
        val secure = try {
            create(context, secureName)
        } catch (e: Exception) {
            context.deleteSharedPreferences(secureName)
            try {
                create(context, secureName)
            } catch (e2: Exception) {
                return context.getSharedPreferences(plainName, Context.MODE_PRIVATE)
            }
        }
        migrateIfNeeded(context, plainName, secure)
        return secure
    }

    private fun create(context: Context, name: String): SharedPreferences {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            context,
            name,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    @Suppress("UNCHECKED_CAST")
    private fun migrateIfNeeded(context: Context, plainName: String, secure: SharedPreferences) {
        val legacy = context.getSharedPreferences(plainName, Context.MODE_PRIVATE)
        val legacyAll = legacy.all
        // Only migrate once: when the legacy store has data and the secure store is empty.
        if (legacyAll.isEmpty() || secure.all.isNotEmpty()) return
        val editor = secure.edit()
        for ((k, v) in legacyAll) {
            when (v) {
                is String -> editor.putString(k, v)
                is Int -> editor.putInt(k, v)
                is Long -> editor.putLong(k, v)
                is Float -> editor.putFloat(k, v)
                is Boolean -> editor.putBoolean(k, v)
                is Set<*> -> editor.putStringSet(k, v as Set<String>)
            }
        }
        editor.apply()
        legacy.edit().clear().apply()
    }
}
