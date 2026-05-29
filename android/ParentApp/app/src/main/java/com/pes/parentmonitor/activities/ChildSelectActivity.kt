package com.pes.parentmonitor.activities

import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.ViewGroup
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.card.MaterialCardView
import com.pes.parentmonitor.R
import com.pes.parentmonitor.api.ChildInfo
import com.pes.parentmonitor.util.PrefsManager

class ChildSelectActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = PrefsManager(this)
        val children: ArrayList<ChildInfoParcel> = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            intent.getParcelableArrayListExtra("children", ChildInfoParcel::class.java)
        } else {
            @Suppress("DEPRECATION")
            intent.getParcelableArrayListExtra("children")
        } ?: arrayListOf()

        if (children.size == 1) {
            // Only one child — skip selection screen
            prefs.childUserId = children[0].userId
            prefs.childName = children[0].name
            startActivity(Intent(this, ParentalDashboardActivity::class.java))
            finish()
            return
        }

        setContentView(R.layout.activity_child_select)
        val rv = findViewById<RecyclerView>(R.id.rvChildren)
        rv.layoutManager = LinearLayoutManager(this)
        rv.adapter = ChildAdapter(children) { child ->
            prefs.childUserId = child.userId
            prefs.childName = child.name
            startActivity(Intent(this, ParentalDashboardActivity::class.java))
            finish()
        }
    }

    data class ChildInfoParcel(
        val userId: Int,
        val name: String,
        val age: Int
    ) : android.os.Parcelable {
        constructor(parcel: android.os.Parcel) : this(
            parcel.readInt(), parcel.readString() ?: "", parcel.readInt()
        )
        override fun writeToParcel(parcel: android.os.Parcel, flags: Int) {
            parcel.writeInt(userId); parcel.writeString(name); parcel.writeInt(age)
        }
        override fun describeContents() = 0
        companion object CREATOR : android.os.Parcelable.Creator<ChildInfoParcel> {
            override fun createFromParcel(p: android.os.Parcel) = ChildInfoParcel(p)
            override fun newArray(size: Int) = arrayOfNulls<ChildInfoParcel>(size)
        }
    }

    private inner class ChildAdapter(
        private val children: List<ChildInfoParcel>,
        private val onClick: (ChildInfoParcel) -> Unit
    ) : RecyclerView.Adapter<ChildAdapter.VH>() {

        inner class VH(val card: MaterialCardView) : RecyclerView.ViewHolder(card) {
            val tvName: TextView = card.findViewById(R.id.tvChildName)
            val tvAge: TextView = card.findViewById(R.id.tvChildAge)
            val tvInitial: TextView = card.findViewById(R.id.tvChildInitial)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val card = layoutInflater.inflate(R.layout.item_child, parent, false) as MaterialCardView
            return VH(card)
        }

        override fun onBindViewHolder(holder: VH, position: Int) {
            val child = children[position]
            holder.tvName.text = child.name
            holder.tvAge.text = "Age ${child.age}"
            holder.tvInitial.text = child.name.firstOrNull()?.uppercase() ?: "?"
            holder.card.setOnClickListener { onClick(child) }
        }

        override fun getItemCount() = children.size
    }
}
