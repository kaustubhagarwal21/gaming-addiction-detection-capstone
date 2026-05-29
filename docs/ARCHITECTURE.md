# Architecture Diagrams

Three views of the system architecture, in increasing detail.

---

## View 1 — Component diagram (high level)

```mermaid
flowchart TB
    subgraph CHILD["Child's Phone"]
        direction TB
        CA[ChildApp UI]
        PMS[PassiveMonitorService<br/>always-on]
        GNS[GameNotificationService]
        CAS[ChatAccessibilityService]
        VRS[VoiceRecorderService<br/>+ Vosk STT]
        SCS[ScreenCaptureService]
        BR[BootReceiver]
    end

    subgraph PARENT["Parent's Phone"]
        PA[ParentApp UI]
        APS[AlertPollingService]
    end

    subgraph BACKEND["Backend Server"]
        API[Flask REST API]
        DB[(SQLite WAL)]
        subgraph ML["ML Subsystem"]
            BM[Behavioral RandomForest]
            CM[Chat TF-IDF + SVC]
            VM[Voice MFCC + RF]
            EN[Ensemble Fusion]
            SH[SHAP Explainer]
            AN[Anomaly Detector]
        end
        BOT[Mira Counselor]
    end

    CA --> API
    PMS --> API
    GNS --> API
    CAS --> API
    VRS --> API
    SCS --> API
    BR -.boot.-> PMS

    PA --> API
    APS --> API

    API --> ML
    API --> AN
    API --> BOT
    API <--> DB
```

---

## View 2 — Data flow (end-to-end session)

```mermaid
sequenceDiagram
    actor Child
    participant PMS as PassiveMonitorService
    participant GMS as GameMonitorService
    participant API as Backend API
    participant ML as ML Ensemble
    participant DB as SQLite

    Note over PMS: Polls UsageStats every 30s
    Child->>PMS: Opens game (e.g. BGMI)
    PMS->>API: POST /api/session/start
    API->>DB: INSERT sessions
    API-->>PMS: {session_id: 42}
    PMS->>GMS: startForegroundService(sid=42)

    loop Every 30 s during session
        GMS->>API: POST /api/session/42/behavioral (20 features)
        GMS->>API: POST /api/session/42/voice (10s WAV)
        GMS->>API: POST /api/session/42/chat (keyboard captures)
        GMS->>API: POST /api/session/42/predict (live risk)
        API->>ML: ensemble prediction
        ML-->>API: {risk: 0.62}
        API-->>GMS: live risk for UI
    end

    Child->>PMS: Leaves game (5min grace)
    PMS->>API: POST /api/session/42/end
    API->>ML: final ensemble + SHAP
    ML-->>API: scores + top_factors
    API->>DB: INSERT predictions + alerts
    API->>API: _update_streak()
    API->>API: _detect_anomalies()
    API-->>PMS: final result
```

---

## View 3 — ML ensemble internals

```mermaid
flowchart LR
    subgraph IN["Inputs"]
        B1[20 behavioral<br/>features]
        B2[Chat text<br/>aggregated]
        B3[Voice WAVs<br/>10s segments]
    end

    subgraph MOD["Per-modality models"]
        M1[Behavior<br/>RandomForest<br/>200 trees]
        M2[Chat<br/>TF-IDF + LinearSVC]
        M3[Voice<br/>MFCC + RandomForest]
    end

    subgraph EN["Ensemble"]
        W[Weighted sum<br/>0.55·b + 0.25·c + 0.20·v]
        G[Genre multiplier<br/>0.7 - 1.25]
        F[Final risk<br/>clip 0 to 1]
        CL[Class:<br/>casual / at_risk / addicted]
    end

    subgraph EX["Explainability"]
        SH[SHAP TreeExplainer]
        TF[Top 3 factors<br/>shown in UI]
    end

    B1 --> M1 --> W
    B2 --> M2 --> W
    B3 --> M3 --> W
    W --> G --> F --> CL

    M1 --> SH --> TF

    CL --> AL[Alerts]
    CL --> ST[Streak update]
    F --> AN[Anomaly check]
```

---

## ASCII Fallback (for plain-text contexts)

```
                 ┌──────────────────────────────────────────────────────┐
                 │              CHILD'S PHONE (ChildApp)                │
                 │                                                      │
                 │  ┌────────────────────────────────────────────────┐  │
                 │  │ PassiveMonitorService  ──  UsageStats polling  │  │
                 │  │ GameNotificationService ── notif craving       │  │
                 │  │ ChatAccessibilityService ── keyboard capture   │  │
                 │  │ VoiceRecorderService  ── Vosk STT + 10s WAVs   │  │
                 │  │ ScreenCaptureService  ── behavior snapshots    │  │
                 │  └────────────────┬───────────────────────────────┘  │
                 └───────────────────┼──────────────────────────────────┘
                                     │
                                     │  HTTP (Retrofit)
                                     ▼
                 ┌──────────────────────────────────────────────────────┐
                 │             BACKEND (Flask, port 5000)               │
                 │                                                      │
                 │   ┌────────────────────────────────────────────┐     │
                 │   │           REST API (40+ endpoints)         │     │
                 │   └─────────────┬──────────────────────────────┘     │
                 │                 │                                    │
                 │     ┌───────────┼──────────────┬──────────────┐      │
                 │     ▼           ▼              ▼              ▼      │
                 │  ┌──────┐  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
                 │  │ ML   │  │ SHAP    │  │ Anomaly  │  │ Mira AI   │  │
                 │  │ 3-mod│  │ explain │  │ z-score  │  │ counselor │  │
                 │  └──┬───┘  └────┬────┘  └────┬─────┘  └─────┬─────┘  │
                 │     │           │            │              │        │
                 │     └───────────┴────────────┴──────────────┘        │
                 │                       │                              │
                 │              ┌────────▼─────────┐                    │
                 │              │  SQLite (WAL)    │                    │
                 │              │  13 tables       │                    │
                 │              └──────────────────┘                    │
                 └─────────────────▲────────────────────────────────────┘
                                   │
                                   │  HTTP (Retrofit)
                                   │
                 ┌─────────────────┴──────────────────────────────────┐
                 │            PARENT'S PHONE (ParentApp)              │
                 │                                                    │
                 │   Dashboard · Alerts · Recommendations · PDF       │
                 │   Multi-child switcher · time-limit control        │
                 └────────────────────────────────────────────────────┘
```
