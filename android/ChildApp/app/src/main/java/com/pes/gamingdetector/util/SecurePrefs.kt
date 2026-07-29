package com.pes.gamingdetector.util

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
 * is still unavailable, it fails closed to an empty local session rather than writing an
 * auth token/captured chat to plaintext.
 */
object SecurePrefs {
    // One instance per prefs file. Building EncryptedSharedPreferences is expensive
    // (Android Keystore access + two Tink keyset managers), and callers construct a
    // PrefsManager on hot paths — the accessibility service used to pay that cost on
    // EVERY key tap, on its main thread. Only the SUCCESS path is cached: while the
    // keystore is broken, each call keeps retrying creation so a recovered keystore
    // is picked up without a process restart.
    private val instances = ConcurrentHashMap<String, SharedPreferences>()
    private val memoryFallbacks = ConcurrentHashMap<String, SharedPreferences>()

    @SuppressLint("ApplySharedPref") // fail-closed/migration ordering must be durable
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
                // Keep launch crash-free, but never silently downgrade secrets to plain
                // XML. Clear any legacy sensitive state and return the now-empty store;
                // the user can retry/login after the device keystore recovers.
                val legacy = context.getSharedPreferences(plainName, Context.MODE_PRIVATE)
                legacy.edit().clear().commit()
                // Never return the plaintext file: PrefsManager would immediately start
                // persisting the next login token/chat queue there. Keep this process
                // usable in memory, while a restart safely requires login again.
                return memoryFallbacks.computeIfAbsent(cacheKey) { MemorySharedPreferences() }
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

    @Suppress("UNCHECKED_CAST")
    private fun migrateIfNeeded(context: Context, plainName: String, secure: SharedPreferences) {
        val legacy = context.getSharedPreferences(plainName, Context.MODE_PRIVATE)
        val legacyAll = legacy.all
        if (legacyAll.isEmpty()) return
        val editor = secure.edit()
        for ((k, v) in legacyAll) {
            // A partial earlier migration may already contain newer encrypted values.
            // Preserve those and copy only missing legacy keys, then durably wipe legacy.
            if (secure.contains(k)) continue
            when (v) {
                is String -> editor.putString(k, v)
                is Int -> editor.putInt(k, v)
                is Long -> editor.putLong(k, v)
                is Float -> editor.putFloat(k, v)
                is Boolean -> editor.putBoolean(k, v)
                is Set<*> -> editor.putStringSet(k, v as Set<String>)
            }
        }
        // Never clear the only durable copy until the encrypted write is on disk. The old
        // apply/apply sequence had a process-death window that could lose the auth/session.
        if (editor.commit()) {
            legacy.edit().clear().commit()
        }
    }
}

/**
 * Process-only SharedPreferences used solely when Android Keystore is unavailable.
 * It deliberately survives component recreation but never writes secrets to disk.
 */
private class MemorySharedPreferences : SharedPreferences {
    private val lock = Any()
    private val values = mutableMapOf<String, Any?>()
    private val listeners =
        CopyOnWriteArraySet<SharedPreferences.OnSharedPreferenceChangeListener>()

    override fun getAll(): MutableMap<String, *> = synchronized(lock) {
        values.mapValues { (_, value) ->
            @Suppress("UNCHECKED_CAST")
            if (value is Set<*>) HashSet(value as Set<String>) else value
        }.toMutableMap()
    }

    override fun getString(key: String?, defValue: String?): String? = synchronized(lock) {
        values[key] as? String ?: defValue
    }

    override fun getStringSet(key: String?, defValues: MutableSet<String>?): MutableSet<String>? =
        synchronized(lock) {
            @Suppress("UNCHECKED_CAST")
            val value = values[key] as? Set<String>
            value?.let(::HashSet) ?: defValues?.let(::HashSet)
        }

    override fun getInt(key: String?, defValue: Int): Int = synchronized(lock) {
        values[key] as? Int ?: defValue
    }

    override fun getLong(key: String?, defValue: Long): Long = synchronized(lock) {
        values[key] as? Long ?: defValue
    }

    override fun getFloat(key: String?, defValue: Float): Float = synchronized(lock) {
        values[key] as? Float ?: defValue
    }

    override fun getBoolean(key: String?, defValue: Boolean): Boolean = synchronized(lock) {
        values[key] as? Boolean ?: defValue
    }

    override fun contains(key: String?): Boolean = synchronized(lock) {
        values.containsKey(key)
    }

    override fun edit(): SharedPreferences.Editor = Editor()

    override fun registerOnSharedPreferenceChangeListener(
        listener: SharedPreferences.OnSharedPreferenceChangeListener?
    ) {
        if (listener != null) listeners += listener
    }

    override fun unregisterOnSharedPreferenceChangeListener(
        listener: SharedPreferences.OnSharedPreferenceChangeListener?
    ) {
        if (listener != null) listeners -= listener
    }

    private inner class Editor : SharedPreferences.Editor {
        private val updates = mutableMapOf<String, Any?>()
        private val removals = mutableSetOf<String>()
        private var clearFirst = false

        override fun putString(key: String?, value: String?): SharedPreferences.Editor = apply {
            if (key != null) updates[key] = value
        }

        override fun putStringSet(
            key: String?,
            values: MutableSet<String>?
        ): SharedPreferences.Editor = apply {
            if (key != null) updates[key] = values?.let(::HashSet)
        }

        override fun putInt(key: String?, value: Int): SharedPreferences.Editor = apply {
            if (key != null) updates[key] = value
        }

        override fun putLong(key: String?, value: Long): SharedPreferences.Editor = apply {
            if (key != null) updates[key] = value
        }

        override fun putFloat(key: String?, value: Float): SharedPreferences.Editor = apply {
            if (key != null) updates[key] = value
        }

        override fun putBoolean(key: String?, value: Boolean): SharedPreferences.Editor = apply {
            if (key != null) updates[key] = value
        }

        override fun remove(key: String?): SharedPreferences.Editor = apply {
            if (key != null) removals += key
        }

        override fun clear(): SharedPreferences.Editor = apply {
            clearFirst = true
        }

        override fun commit(): Boolean {
            val changed = mutableSetOf<String>()
            synchronized(lock) {
                if (clearFirst) {
                    changed += values.keys
                    values.clear()
                }
                for (key in removals) {
                    if (values.remove(key) != null) changed += key
                }
                for ((key, value) in updates) {
                    if (value == null) {
                        if (values.remove(key) != null) changed += key
                    } else {
                        values[key] = if (value is Set<*>) HashSet(value) else value
                        changed += key
                    }
                }
            }
            for (key in changed) {
                for (listener in listeners) {
                    listener.onSharedPreferenceChanged(this@MemorySharedPreferences, key)
                }
            }
            return true
        }

        override fun apply() {
            commit()
        }
    }
}
