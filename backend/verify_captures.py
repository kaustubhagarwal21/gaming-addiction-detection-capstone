"""
Manual verification tool for chat + voice captures.

Dumps every chat message and voice-emotion event stored for a session, so you
can confirm the Android pipeline is actually delivering data. Audio WAV files
are deleted after feature extraction (privacy), so voice playback isn't
possible — only the analysed emotion/intensity is retained.

Usage:
    python verify_captures.py                       # latest session, full dump
    python verify_captures.py --live                # *** RECOMMENDED FOR TESTING ***
                                                    # waits for a session, then streams
                                                    # every chat and voice event live
    python verify_captures.py --session 100         # specific session
    python verify_captures.py --user 1              # latest session for user 1
    python verify_captures.py --tail                # tail the latest session only
    python verify_captures.py --limit 20            # cap message list
    python verify_captures.py --play 5              # open the 5th voice WAV in the
                                                    # default audio app (needs KEEP_AUDIO=1
                                                    # set when the backend recorded it)

To retain raw audio for playback during testing, start the backend with:
    $env:KEEP_AUDIO=1; python app.py  (PowerShell)
    KEEP_AUDIO=1 python app.py        (bash)
"""
import argparse
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(BASE_DIR, 'gaming_addiction.db')
AUDIO_DIR = os.path.join(BASE_DIR, 'audio_uploads')


def connect() -> sqlite3.Connection:
    if not os.path.exists(DB_PATH):
        sys.exit(f"DB not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def latest_session(conn: sqlite3.Connection, user_id: int | None) -> sqlite3.Row | None:
    if user_id is not None:
        q = """SELECT * FROM sessions WHERE user_id = ?
               ORDER BY start_time DESC LIMIT 1"""
        return conn.execute(q, (user_id,)).fetchone()
    return conn.execute(
        "SELECT * FROM sessions ORDER BY start_time DESC LIMIT 1"
    ).fetchone()


def fmt_ts(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M:%S")
    except Exception:
        return iso or ""


def print_session_header(s: sqlite3.Row) -> None:
    print()
    print("=" * 78)
    print(f"  Session {s['session_id']}   user={s['user_id']}   game={s['game_name']!r}")
    print(f"  start={s['start_time']}   end={s['end_time'] or '(active)'}")
    dur = s['duration_seconds']
    if dur:
        m, sec = divmod(int(dur), 60)
        print(f"  duration={m}m {sec}s   risk={s['risk_category']}  score={s['final_risk_score']}")
    print("=" * 78)


def dump_chats(conn: sqlite3.Connection, sid: int, limit: int) -> int:
    rows = conn.execute(
        "SELECT timestamp, source, message FROM chat_messages "
        "WHERE session_id = ? ORDER BY id ASC", (sid,)
    ).fetchall()
    total = len(rows)
    print(f"\n  CHAT MESSAGES ({total})")
    print("  " + "-" * 76)
    if not rows:
        print("    (none)")
        return 0
    shown = rows[-limit:] if limit and total > limit else rows
    if len(shown) < total:
        print(f"    ... ({total - len(shown)} earlier message(s) hidden — pass --limit 0 to see all)")
    for r in shown:
        src = (r['source'] or '?').ljust(10)
        ts  = fmt_ts(r['timestamp']).ljust(10)
        msg = (r['message'] or '').replace('\n', ' ').strip()
        if len(msg) > 80:
            msg = msg[:77] + '...'
        print(f"    [{ts}] {src} {msg}")
    by_source = {}
    for r in rows:
        by_source[r['source'] or '?'] = by_source.get(r['source'] or '?', 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(by_source.items()))
    print(f"  -- by source: {summary}")
    return total


def dump_voice(conn: sqlite3.Connection, sid: int, limit: int) -> int:
    rows = conn.execute(
        "SELECT timestamp, emotion, intensity, duration_s, audio_file "
        "FROM voice_events WHERE session_id = ? ORDER BY id ASC", (sid,)
    ).fetchall()
    total = len(rows)
    print(f"\n  VOICE EVENTS ({total})")
    print("  " + "-" * 76)
    if not rows:
        print("    (none)")
        return 0
    shown = rows[-limit:] if limit and total > limit else rows
    if len(shown) < total:
        print(f"    ... ({total - len(shown)} earlier event(s) hidden — pass --limit 0 to see all)")
    for idx, r in enumerate(shown, start=1):
        ts  = fmt_ts(r['timestamp']).ljust(10)
        emo = (r['emotion'] or '?').ljust(12)
        intensity = r['intensity']
        intensity_str = f"{intensity:.2f}" if intensity is not None else "--"
        dur = r['duration_s']
        dur_str = f"{dur:.1f}s" if dur is not None else "--"
        af = f"  WAV={r['audio_file']}" if r['audio_file'] else ""
        print(f"  {idx:>3}. [{ts}] {emo} intensity={intensity_str}  dur={dur_str}{af}")
    by_emo = {}
    for r in rows:
        by_emo[r['emotion'] or '?'] = by_emo.get(r['emotion'] or '?', 0) + 1
    summary = ", ".join(f"{k}={v}" for k, v in sorted(by_emo.items()))
    print(f"  -- emotions: {summary}")
    return total


def list_recent_sessions(conn: sqlite3.Connection) -> None:
    print("\nRecent sessions (newest first):")
    q = """SELECT s.session_id, s.user_id, s.game_name, s.start_time, s.end_time,
                  (SELECT COUNT(*) FROM chat_messages WHERE session_id=s.session_id) AS chats,
                  (SELECT COUNT(*) FROM voice_events  WHERE session_id=s.session_id) AS voices
           FROM sessions s ORDER BY s.start_time DESC LIMIT 10"""
    for r in conn.execute(q):
        active = "(active)" if not r['end_time'] else ""
        print(f"  #{r['session_id']:>4}  user={r['user_id']}  {r['game_name']:<20}"
              f"  chats={r['chats']:>3}  voice={r['voices']:>3}  {r['start_time']} {active}")


def live_monitor(conn: sqlite3.Connection) -> None:
    """Stream chat + voice captures for whichever session is currently active.
    Auto-detects session start/end. Ctrl-C to exit."""
    keep_audio = os.path.exists(AUDIO_DIR) and any(
        f.endswith('.wav') for f in os.listdir(AUDIO_DIR)
    ) if os.path.exists(AUDIO_DIR) else False
    print()
    print("=" * 78)
    print("  LIVE CAPTURE MONITOR")
    print("=" * 78)
    print(f"  DB:    {DB_PATH}")
    print(f"  Audio: {AUDIO_DIR}  " + ("(retaining WAVs)" if keep_audio else "(WAVs deleted after analysis — set KEEP_AUDIO=1 on the backend to keep them)"))
    print()
    print("  Waiting for an active session. Open a game on the child device to start.")
    print("  Ctrl-C to stop.\n")

    current_sid: int | None = None
    last_chat_id = 0
    last_voice_id = 0
    last_idle_print = 0.0

    try:
        while True:
            row = conn.execute(
                "SELECT * FROM sessions WHERE end_time IS NULL ORDER BY start_time DESC LIMIT 1"
            ).fetchone()

            if row is None:
                if current_sid is not None:
                    # Session we were following just ended — print a footer
                    ended = conn.execute(
                        "SELECT * FROM sessions WHERE session_id = ?", (current_sid,)
                    ).fetchone()
                    if ended:
                        dur = ended['duration_seconds']
                        risk = ended['risk_category'] or '?'
                        score = ended['final_risk_score']
                        score_str = f"{score:.2f}" if score is not None else "--"
                        print(f"\n  -- Session {current_sid} ended"
                              f"  duration={dur or 0}s  risk={risk}  score={score_str}\n")
                    current_sid = None
                    last_chat_id = 0
                    last_voice_id = 0
                now = time.time()
                if now - last_idle_print > 60:
                    print(f"  ... idle ({datetime.now().strftime('%H:%M:%S')} — waiting for a session)")
                    last_idle_print = now
                time.sleep(2)
                continue

            if row['session_id'] != current_sid:
                current_sid = row['session_id']
                last_chat_id = 0
                last_voice_id = 0
                print_session_header(row)
                print("  Streaming live...\n")

            # New chats
            for c in conn.execute(
                "SELECT * FROM chat_messages WHERE session_id=? AND id > ? ORDER BY id",
                (current_sid, last_chat_id)
            ).fetchall():
                ts  = fmt_ts(c['timestamp'])
                src = (c['source'] or '?').upper().ljust(14)
                msg = (c['message'] or '').replace('\n', ' ').strip()
                if len(msg) > 110:
                    msg = msg[:107] + '...'
                print(f"  [{ts}] CHAT  {src} {msg}")
                last_chat_id = c['id']

            # New voice events
            for v in conn.execute(
                "SELECT * FROM voice_events WHERE session_id=? AND id > ? ORDER BY id",
                (current_sid, last_voice_id)
            ).fetchall():
                ts  = fmt_ts(v['timestamp'])
                emo = (v['emotion'] or '?').ljust(12)
                intensity = v['intensity']
                intensity_str = f"{intensity:.2f}" if intensity is not None else "--"
                dur = v['duration_s']
                dur_str = f"{dur:.1f}s".ljust(6) if dur is not None else "--    "
                if v['audio_file']:
                    full_path = os.path.join(AUDIO_DIR, v['audio_file'])
                    af = f"  WAV={full_path}"
                else:
                    af = ""
                print(f"  [{ts}] VOICE {emo}  i={intensity_str}  dur={dur_str}{af}")
                last_voice_id = v['id']

            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopped.")


def tail(conn: sqlite3.Connection, sid: int) -> None:
    print(f"\nTailing session {sid}.  Ctrl-C to exit.")
    last_chat = conn.execute("SELECT COALESCE(MAX(id), 0) FROM chat_messages WHERE session_id=?", (sid,)).fetchone()[0]
    last_voice = conn.execute("SELECT COALESCE(MAX(id), 0) FROM voice_events  WHERE session_id=?", (sid,)).fetchone()[0]
    try:
        while True:
            for r in conn.execute(
                "SELECT id, timestamp, source, message FROM chat_messages WHERE session_id=? AND id > ? ORDER BY id",
                (sid, last_chat)
            ).fetchall():
                ts = fmt_ts(r['timestamp'])
                print(f"  CHAT  [{ts}] {(r['source'] or '?'):>10}  {r['message']}")
                last_chat = r['id']
            for r in conn.execute(
                "SELECT id, timestamp, emotion, intensity FROM voice_events WHERE session_id=? AND id > ? ORDER BY id",
                (sid, last_voice)
            ).fetchall():
                ts = fmt_ts(r['timestamp'])
                intensity = r['intensity']
                intensity_str = f"{intensity:.2f}" if intensity is not None else "--"
                print(f"  VOICE [{ts}] {(r['emotion'] or '?'):>10}  intensity={intensity_str}")
                last_voice = r['id']
            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\nstopped.")


def play_wav(conn: sqlite3.Connection, sid: int, idx: int) -> None:
    rows = conn.execute(
        "SELECT audio_file FROM voice_events WHERE session_id=? AND audio_file IS NOT NULL ORDER BY id",
        (sid,)
    ).fetchall()
    if not rows:
        sys.exit("No retained WAVs for this session. Restart the backend with KEEP_AUDIO=1 first.")
    if idx < 1 or idx > len(rows):
        sys.exit(f"--play {idx} out of range; session has {len(rows)} retained WAV(s).")
    path = os.path.join(AUDIO_DIR, rows[idx - 1]['audio_file'])
    if not os.path.exists(path):
        sys.exit(f"File missing on disk: {path}")
    print(f"Opening {path} ...")
    if sys.platform == 'win32':
        os.startfile(path)
    elif sys.platform == 'darwin':
        subprocess.Popen(['open', path])
    else:
        subprocess.Popen(['xdg-open', path])


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--session', type=int, help="session_id to inspect (default: latest)")
    p.add_argument('--user',    type=int, help="user_id; picks that user's latest session")
    p.add_argument('--limit',   type=int, default=30,
                   help="cap per-list output (0 = no cap; default 30)")
    p.add_argument('--list',    action='store_true', help="just list recent sessions")
    p.add_argument('--live',    action='store_true',
                   help="auto-follow whatever session is active; print captures live "
                        "until you Ctrl-C. Best for testing while playing.")
    p.add_argument('--tail',    action='store_true',
                   help="live-tail incoming captures for the chosen session")
    p.add_argument('--play',    type=int, metavar='N',
                   help="open the Nth retained voice WAV in your default audio player")
    args = p.parse_args()

    conn = connect()

    if args.list:
        list_recent_sessions(conn)
        return

    if args.live:
        live_monitor(conn)
        return

    if args.session is not None:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (args.session,)).fetchone()
        if not row:
            sys.exit(f"No session with id={args.session}")
    else:
        row = latest_session(conn, args.user)
        if not row:
            sys.exit("No sessions in DB yet — start one on the device first.")

    print_session_header(row)
    if args.tail:
        tail(conn, row['session_id'])
        return
    if args.play is not None:
        play_wav(conn, row['session_id'], args.play)
        return

    n_chat  = dump_chats(conn,  row['session_id'], args.limit)
    n_voice = dump_voice(conn,  row['session_id'], args.limit)

    print()
    if n_chat == 0 and n_voice == 0:
        print("  Nothing has been captured for this session.")
        print("  - For chat: make sure the Accessibility service is ON, then type in any chat field")
        print("    (WhatsApp, in-game chat, SMS) for at least 3 characters and tap send.")
        print("  - For voice: make sure microphone permission was granted and that the")
        print("    GameMonitorService is running (yellow notification visible).")
    else:
        print(f"  -> {n_chat} chat message(s), {n_voice} voice event(s) for session {row['session_id']}.")
    print()


if __name__ == '__main__':
    main()
