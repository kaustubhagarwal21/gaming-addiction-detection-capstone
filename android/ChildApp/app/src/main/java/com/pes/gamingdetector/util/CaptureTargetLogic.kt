package com.pes.gamingdetector.util

/** Fail-closed package matching shared by the two typed-chat capture paths. */
object CaptureTargetLogic {
    fun isExactSessionTarget(trackedPackage: String?, editorPackage: String?): Boolean {
        val tracked = trackedPackage?.trim().orEmpty()
        val editor = editorPackage?.trim().orEmpty()
        return tracked.isNotEmpty() && editor.isNotEmpty() && tracked == editor
    }
}
