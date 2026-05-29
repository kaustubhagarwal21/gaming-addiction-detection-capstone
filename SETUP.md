# Gaming Addiction Detector — Setup Guide
**PES University Capstone PW26_SJ_05**
Team: Kaustubh Agarwal, Kanak Goyal, Khushee P Kiran, Vidisha Murali

---

## Architecture Overview

```
ChildApp (child's phone)  ──┐
                             ├──► Flask REST API (your PC) ──► ML Models (.pkl)
ParentApp (parent's phone) ─┘        ↓
                                  SQLite DB
                              (gaming_addiction.db)
```

Two separate Android apps talk to the **same Flask backend**:
- **ChildApp** (`com.pes.gamingdetector`) — installed on the child's phone
- **ParentApp** (`com.pes.parentmonitor`) — installed on the parent's phone

---

## STEP 1 — Start the Backend (Flask API)

### Prerequisites
- Python 3.9+
- pip

### Install & Run

```bash
cd C:\Users\KAUSTUBH\Desktop\capstone_main\backend

python -m venv venv
venv\Scripts\activate          # Windows

pip install -r requirements.txt

python app.py
```

The server starts on **http://0.0.0.0:5000**

### Find your PC's IP address
```
ipconfig    # Windows
```
Look for the IPv4 address under your WiFi adapter (e.g., `192.168.1.100`).

---

## STEP 2 — Open the Android Apps in Android Studio

### ChildApp
1. **File → Open** → `C:\Users\KAUSTUBH\Desktop\capstone_main\android\ChildApp`
2. Wait for Gradle sync
3. Set your server IP in [Constants.kt](android/ChildApp/app/src/main/java/com/pes/gamingdetector/util/Constants.kt):
   ```kotlin
   const val BASE_URL = "http://192.168.1.100:5000/"   // ← YOUR PC's IP
   ```
4. Run on the **child's** device

### ParentApp
1. **File → Open** → `C:\Users\KAUSTUBH\Desktop\capstone_main\android\ParentApp`
2. Wait for Gradle sync
3. Set your server IP in [Constants.kt](android/ParentApp/app/src/main/java/com/pes/parentmonitor/util/Constants.kt):
   ```kotlin
   const val BASE_URL = "http://192.168.1.100:5000/"   // ← YOUR PC's IP
   ```
4. Run on the **parent's** device

> **Note:** Both devices must be on the **same WiFi network** as the PC running the backend.

---

## STEP 3 — Android Permissions (ChildApp Only)

The ChildApp needs special permissions granted manually:

### a) Usage Stats Permission (game detection)
```
Settings → Apps → Special App Access → Usage Access → Gaming Detector → Allow
```

### b) Microphone Permission
Granted automatically on first session start via runtime prompt.

### c) Display over other apps (optional overlay)
```
Settings → Apps → Special App Access → Display over other apps → Allow
```

---

## STEP 4 — Demo Credentials

| Role   | PIN  | App        |
|--------|------|------------|
| Child  | 1234 | ChildApp   |
| Parent | 0000 | ParentApp  |

The backend seeds a default user (PIN 1234, parent PIN 0000) on first run.

---

## STEP 5 — Using the Apps

### ChildApp Flow:
1. Login with PIN `1234`
2. Select a game from the grid (e.g., PUBG Mobile)
3. Tap **▶ Start Session** — monitoring begins
4. Grant microphone permission when prompted
5. Play your game
6. Return and tap **⏹ End Session** — risk prediction is generated
7. Tap **📊 My Dashboard** to see risk history and trend

### ParentApp Flow:
1. Login with PIN `0000`
2. View the **Dashboard** — child's current risk, weekly hours, late-night count
3. Pull down to refresh at any time
4. Tap **🔔 Alerts** to see risk change notifications
5. Tap **Tips** to read tailored recommendations
6. The app polls the backend every 60s and sends push notifications on risk changes

---

## Backend API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/api/health` | Server health + models_loaded status |
| POST   | `/api/user/login` | Login (role: child \| parent) |
| POST   | `/api/session/start` | Start a gaming session |
| POST   | `/api/session/{id}/end` | End session + full prediction |
| POST   | `/api/session/{id}/behavioral` | Post behavioral data |
| POST   | `/api/session/{id}/predict` | Live intermediate prediction |
| POST   | `/api/session/{id}/voice` | Upload voice WAV for analysis |
| POST   | `/api/session/{id}/chat` | Save chat/OCR message |
| GET    | `/api/dashboard/user` | Child dashboard data |
| GET    | `/api/dashboard/parent` | Parent dashboard data |
| GET    | `/api/alerts` | Get alerts for a user |
| POST   | `/api/alerts/mark_read` | Mark alerts as read |
| GET    | `/api/child/status` | Is child currently playing? |
| GET    | `/api/games` | List of supported games |

### Test the API in browser:
```
http://192.168.1.100:5000/api/health
http://192.168.1.100:5000/api/games
```

---

## ML Models (3-Model Ensemble)

| Model    | File                 | Algorithm                         | Weight |
|----------|----------------------|-----------------------------------|--------|
| Behavior | `behavior_model.pkl` | Random Forest (20 IAT features)   | 40%    |
| Chat     | `chat_model.pkl` + `tfidf_vectorizer.pkl` | TF-IDF + Regression | 35% |
| Voice    | `voice_model.pkl`    | Gradient Boosting (17 MFCC+pitch+energy) | 25% |

**Output:** Casual / At-Risk / Addicted

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Cannot reach server" | Check IP in Constants.kt matches your PC's IP. Both on same WiFi? |
| Models not loading | Run `python app.py` and check console for model load errors |
| No voice analysis | Ensure microphone permission granted. Check if librosa is installed |
| Gradle sync fails | File → Invalidate Caches → Restart. Check internet for dependency download |
| App crashes on start | Check logcat for error. Usually a missing resource file |
| ParentApp shows no data | Check child_user_id in ParentApp Settings equals the child's user_id (default: 1) |
| Alerts not appearing | Ensure AlertPollingService is running; check notification permissions |

---

## Project Structure

```
capstone_main/
├── backend/                         Flask REST API
│   ├── app.py                       Main server (all endpoints + ML logic)
│   ├── requirements.txt
│   └── models/                      Trained ML model files (.pkl)
│
└── android/
    ├── ChildApp/                    Installed on child's phone
    │   └── app/src/main/
    │       ├── java/com/pes/gamingdetector/
    │       │   ├── activities/      Login, Home, Session, Dashboard, Settings
    │       │   ├── services/        GameMonitor, VoiceRecorder, ScreenCapture, Boot
    │       │   ├── api/             Models, ApiService, ApiClient
    │       │   └── util/            Constants, PrefsManager
    │       └── res/                 layouts, drawables, values
    │
    ├── ParentApp/                   Installed on parent's phone
    │   └── app/src/main/
    │       ├── java/com/pes/parentmonitor/
    │       │   ├── activities/      Login, ParentalDashboard, Alerts, Recommendations, Settings
    │       │   ├── service/         AlertPollingService, BootReceiver
    │       │   ├── api/             Models, ApiService, ApiClient
    │       │   └── util/            Constants, PrefsManager
    │       └── res/                 layouts, drawables, values
    │
    └── GamingAddictionDetector/     (Legacy single-app — superseded by above two)
```
