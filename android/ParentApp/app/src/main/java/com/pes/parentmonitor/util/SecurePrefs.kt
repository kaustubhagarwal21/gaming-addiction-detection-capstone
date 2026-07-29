package com.pes.parentmonitor.util

import android.annotation.SuppressLint
import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CopyOnWriteArraySet

/**
 * Returns an [EncryptedSharedPreferences]-backed store so sensitive values (the auth
 * token, in particular) are encrypted at rest instead of sitting in plaintext XML that
 * any rooted device or backup extraction could read.
 *
 * It implements the same [SharedPreferences] interface, so PrefsManager is otherwise
 * unchanged. On first run it transparently migrates any values from the legacy plaintext
 * store, then wipes it. If the encrypted keyset is ever unreadable (restored backup,
 * keystore reset) it rebuilds the store (worst case: a one-time re-login). If encryption
 * remains unavailable, writes stay in process memory instead of silently downgrading the
 * auth token to plaintext.
 */
object SecurePrefs {
    // One instance per prefs file. Building EncryptedSharedPreferences is expensive
    // (Android Keystore access + two Tink keyset managers), and PrefsManager is
    // constructed per Activity/Service/FCM message — rebuilding the store each time
    // paid that cost repeatedly. Only the SUCCESS path is cached: while the keystore
    // is broken each call keeps retrying creation, so a recovered keystore is picked
    // up without a process restart.
    private val instances = ConcurrentHashMap<String, SharedPreferences>()
    private val memoryFallbacks = ConcurrentHashMap<String, SharedPreferences>()

    @SuppressLint("ApplySharedPref") // migration ordering intentionally requires durable writes
    fun get(context: Context, plainName: String): SharedPreferences {
        val cacheKey = "${context.packageName}:$plainName"
        instances[cacheKey]?.let { return it }
        val secureName = plainName + "_secure"
        val secure = try {
            create(context, secureName)
        } catch (e: Exception) {
            context.deleteSharedPreferences(secureName)
            try {
                create(context, secureName)
            } catch (e2: Exception) {
                // Never return the legacy plaintext store: callers would continue writing
                // tokens to disk. A shared process-memory store keeps the app crash-free
                // while failing closed to a non-durable session until Keystore recovers.
                // Also remove any pre-migration plaintext token. Leaving it readable on
                // disk would defeat the fail-closed fallback even though future writes
                // stay in memory.
                context.getSharedPreferences(plainName, Context.MODE_PRIVATE)
                    .edit()
                    .clear()
                    .commit()
                val memoryKey = "${context.packageName}:$secureName"
                return memoryFallbacks.getOrPut(memoryKey) { MemoryPreferences() }
            }
        }
        migrateIfNeeded(context, plainName, secure)
        // Racing first callers may each build an instance; both wrap the same file, and
        // exactly one becomes the canonical cached copy every later call returns.
        return instances.putIfAbsent(cacheKey, secure) ?: secure
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

    @SuppressLint("ApplySharedPref") // plaintext is wiped only after encrypted data is durable
    private fun migrateIfNeeded(context: Context, plainName: String, secure: SharedPreferences) {
        val legacy = context.getSharedPreferences(plainName, Context.MODE_PRIVATE)
        val legacyAll = legacy.all
        if (legacyAll.isEmpty()) return

        // Merge missing keys rather than requiring the secure store to be completely
        // empty. That makes migration recoverable if a previous version populated one
        // secure preference before the legacy copy was migrated.
        val editor = secure.edit()
        var changed = false
        var representable = true
        for ((k, v) in legacyAll) {
            if (secure.contains(k)) continue
            when (v) {
                is String -> editor.putString(k, v).also { changed = true }
                is Int -> editor.putInt(k, v).also { changed = true }
                is Long -> editor.putLong(k, v).also { changed = true }
                is Float -> editor.putFloat(k, v).also { changed = true }
                is Boolean -> editor.putBoolean(k, v).also { changed = true }
                is Set<*> -> {
                    val strings = v.filterIsInstance<String>().toSet()
                    if (strings.size == v.size) {
                        editor.putStringSet(k, strings)
                        changed = true
                    } else {
                        representable = false
                    }
                }
                else -> representable = false
            }
        }

        // Never erase the only durable copy first. commit() establishes that every
        // supported legacy value is on encrypted storage before clearing plaintext.
        val encryptedCopyDurable = !changed || editor.commit()
        if (representable && encryptedCopyDurable) {
            legacy.edit().clear().commit()
        }
    }

    /**
     * Minimal process-local [SharedPreferences] used only when Android Keystore cannot
     * create encrypted storage. It deliberately has no disk backing.
     */
    private class MemoryPreferences : SharedPreferences {
        private val values = LinkedHashMap<String, Any>()
        private val listeners =
            CopyOnWriteArraySet<SharedPreferences.OnSharedPreferenceChangeListener>()

        override fun getAll(): Map<String, *> = synchronized(values) {
            values.mapValues { (_, value) ->
                if (value is Set<*>) value.toSet() else value
            }
        }

        override fun getString(key: String, defValue: String?): String? =
            synchronized(values) { values[key] as? String ?: defValue }

        override fun getStringSet(key: String, defValues: Set<String>?): Set<String>? =
            synchronized(values) {
                @Suppress("UNCHECKED_CAST")
                ((values[key] as? Set<String>)?.toSet()) ?: defValues
            }

        override fun getInt(key: String, defValue: Int): Int =
            synchronized(values) { values[key] as? Int ?: defValue }

        override fun getLong(key: String, defValue: Long): Long =
            synchronized(values) { values[key] as? Long ?: defValue }

        override fun getFloat(key: String, defValue: Float): Float =
            synchronized(values) { values[key] as? Float ?: defValue }

        override fun getBoolean(key: String, defValue: Boolean): Boolean =
            synchronized(values) { values[key] as? Boolean ?: defValue }

        override fun contains(key: String): Boolean = synchronized(values) {
            values.containsKey(key)
        }

        override fun edit(): SharedPreferences.Editor = MemoryEditor()

        override fun registerOnSharedPreferenceChangeListener(
            listener: SharedPreferences.OnSharedPreferenceChangeListener
        ) {
            listeners += listener
        }

        override fun unregisterOnSharedPreferenceChangeListener(
            listener: SharedPreferences.OnSharedPreferenceChangeListener
        ) {
            listeners -= listener
        }

        private inner class MemoryEditor : SharedPreferences.Editor {
            private val pending = LinkedHashMap<String, Any?>()
            private var clearRequested = false

            override fun putString(key: String, value: String?) = apply {
                pending[key] = value
            }

            override fun putStringSet(key: String, values: Set<String>?) = apply {
                pending[key] = values?.toSet()
            }

            override fun putInt(key: String, value: Int) = apply { pending[key] = value }
            override fun putLong(key: String, value: Long) = apply { pending[key] = value }
            override fun putFloat(key: String, value: Float) = apply { pending[key] = value }
            override fun putBoolean(key: String, value: Boolean) = apply { pending[key] = value }
            override fun remove(key: String) = apply { pending[key] = null }
            override fun clear() = apply { clearRequested = true }

            override fun commit(): Boolean {
                applyChanges()
                return true
            }

            override fun apply() = applyChanges()

            private fun applyChanges() {
                val changedKeys = linkedSetOf<String>()
                synchronized(values) {
                    if (clearRequested) {
                        changedKeys += values.keys
                        values.clear()
                    }
                    pending.forEach { (key, value) ->
                        val old = values[key]
                        if (value == null) {
                            if (values.remove(key) != null) changedKeys += key
                        } else if (old != value) {
                            values[key] = value
                            changedKeys += key
                        }
                    }
                }
                // Match platform SharedPreferences.Editor semantics: once a commit/apply
                // completes, a reused editor must not replay old puts or clear requests.
                pending.clear()
                clearRequested = false
                changedKeys.forEach { key ->
                    listeners.forEach { listener ->
                        listener.onSharedPreferenceChanged(this@MemoryPreferences, key)
                    }
                }
            }
        }
    }
}
