#!/usr/bin/env python3
"""
AquaFeed - Raspberry Pi API Server
Run on each Pi with: python3 server.py
Install deps: pip install flask flask-cors

On first run it generates a unique auth token (feeder_token.txt) and prints it.
Copy that token into the UI when adding the tank.
"""

import subprocess, json, threading, secrets
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
# Allow the custom auth header through CORS preflight
CORS(app, allow_headers=["Content-Type", "X-Auth-Token"])

BASE_DIR     = Path(__file__).parent
CONFIG_FILE  = BASE_DIR / "feeder_config.json"
FEED_BIN     = BASE_DIR / "feed"        # compiled C++ binary (from feed.cpp)
LOG_FILE     = BASE_DIR / "feed_log.json"
TOKEN_FILE   = BASE_DIR / "feeder_token.txt"

DEFAULT_CONFIG = {
    "tank_name": "Fish Tank",
    "feed_interval_days": 1,
    "rotation_angle": 90,
    "enabled": False,
    "next_feed_time": None,
    "min_feed_gap_hours": 6,   # overfeeding lockout window
}

feed_lock  = threading.Lock()
is_feeding = False


# ── Auth token ────────────────────────────────────────────────────────────────
def get_token():
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    tok = secrets.token_hex(16)
    TOKEN_FILE.write_text(tok)
    return tok

TOKEN = get_token()

@app.before_request
def check_auth():
    if request.method == "OPTIONS":
        return  # let CORS preflight through unauthenticated
    supplied = request.headers.get("X-Auth-Token", "")
    if not secrets.compare_digest(supplied, TOKEN):
        return jsonify({"error": "Unauthorized"}), 401


# ── Config helpers ────────────────────────────────────────────────────────────
def load_config():
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text())
        for k, v in DEFAULT_CONFIG.items():
            data.setdefault(k, v)
        return data
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))


# ── Log helpers ───────────────────────────────────────────────────────────────
def load_log():
    return json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []

def append_log(entry):
    log = load_log()[-99:]   # keep last 100
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2))

def last_success_dt():
    """Timestamp of the most recent real (non-skipped) successful feed."""
    for e in reversed(load_log()):
        if e.get("success") and not e.get("skipped"):
            try:
                return datetime.fromisoformat(e["timestamp"])
            except (ValueError, TypeError):
                continue
    return None


# ── Overfeeding guard ─────────────────────────────────────────────────────────
def gap_block(cfg, triggered_by, force):
    """Return next-allowed ISO string if a feed should be blocked, else None.
    The Test button (triggered_by == 'test') and force=True always bypass."""
    if triggered_by == "test" or force:
        return None
    last = last_success_dt()
    if last is None:
        return None
    gap = timedelta(hours=float(cfg.get("min_feed_gap_hours", 6)))
    if datetime.now() - last < gap:
        return (last + gap).isoformat()
    return None


# ── Feed execution ────────────────────────────────────────────────────────────
def run_feed(angle, triggered_by="manual", force=False):
    global is_feeding
    cfg = load_config()

    blocked_until = gap_block(cfg, triggered_by, force)
    if blocked_until:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "angle": angle, "triggered_by": triggered_by,
            "success": False, "skipped": True,
            "error": f"Skipped: fed within last {cfg.get('min_feed_gap_hours', 6)}h",
            "next_allowed": blocked_until,
        }
        append_log(entry)
        return {"success": False, "skipped": True,
                "error": entry["error"], "next_allowed": blocked_until}

    with feed_lock:
        if is_feeding:
            return {"success": False, "error": "Already feeding"}
        is_feeding = True
    try:
        res = subprocess.run(
            [str(FEED_BIN), "--angle", str(angle)],
            capture_output=True, text=True, timeout=60
        )
        entry = {
            "timestamp": datetime.now().isoformat(),
            "angle": angle, "triggered_by": triggered_by,
            "success": res.returncode == 0,
            "stdout": res.stdout.strip(), "stderr": res.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        entry = {"timestamp": datetime.now().isoformat(), "angle": angle,
                 "triggered_by": triggered_by, "success": False,
                 "error": "Timed out after 60 s"}
    except Exception as e:
        entry = {"timestamp": datetime.now().isoformat(), "angle": angle,
                 "triggered_by": triggered_by, "success": False, "error": str(e)}
    finally:
        with feed_lock:
            is_feeding = False
    append_log(entry)
    return {"success": entry.get("success", False), "log": entry}


# ── Scheduler ─────────────────────────────────────────────────────────────────
_stop = threading.Event()

def _scheduler():
    while not _stop.wait(30):
        cfg = load_config()
        if not (cfg.get("enabled") and cfg.get("next_feed_time")):
            continue
        try:
            scheduled = datetime.fromisoformat(cfg["next_feed_time"])
        except (ValueError, TypeError):
            continue

        now = datetime.now()
        if now >= scheduled:
            # Fire at most one feed (overfeeding guard may skip it).
            run_feed(cfg.get("rotation_angle", 90), "scheduler")

            # Anchor the next feed to the SCHEDULED time (no drift), and skip
            # any windows we missed while powered off (no catch-up burst).
            interval = timedelta(days=float(cfg.get("feed_interval_days", 1)))
            nxt = scheduled + interval
            while nxt <= now:
                nxt += interval
            cfg["next_feed_time"] = nxt.isoformat()
            save_config(cfg)

threading.Thread(target=_scheduler, daemon=True).start()


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/api/status")
def get_status():
    cfg = load_config()
    log = load_log()
    real = [e for e in log if not e.get("skipped")]
    return jsonify({"status": "ok", "is_feeding": is_feeding,
                    "config": cfg, "last_feed": real[-1] if real else None})

@app.post("/api/config")
def update_config():
    data = request.json or {}
    cfg  = load_config()
    if "tank_name"          in data: cfg["tank_name"] = str(data["tank_name"])
    if "feed_interval_days" in data:
        v = float(data["feed_interval_days"])
        if v <= 0: return jsonify({"error": "must be > 0"}), 400
        cfg["feed_interval_days"] = v
    if "rotation_angle"     in data:
        v = float(data["rotation_angle"])
        if not (1 <= v <= 360): return jsonify({"error": "must be 1-360"}), 400
        cfg["rotation_angle"] = v
    if "min_feed_gap_hours" in data:
        v = float(data["min_feed_gap_hours"])
        if v < 0: return jsonify({"error": "must be >= 0"}), 400
        cfg["min_feed_gap_hours"] = v
    if "enabled"            in data: cfg["enabled"]        = bool(data["enabled"])
    if "next_feed_time"     in data: cfg["next_feed_time"] = data["next_feed_time"]
    save_config(cfg)
    return jsonify({"success": True, "config": cfg})

@app.post("/api/feed/now")
def feed_now():
    if is_feeding:
        return jsonify({"success": False, "error": "Already feeding"}), 409
    cfg   = load_config()
    body  = request.json or {}
    angle = body.get("angle", cfg.get("rotation_angle", 90))
    by    = body.get("triggered_by", "manual")
    force = bool(body.get("force", False))

    # Synchronous overfeeding check so the UI can prompt to override.
    blocked_until = gap_block(cfg, by, force)
    if blocked_until:
        return jsonify({"success": False, "skipped": True,
                        "error": f"Fed within last {cfg.get('min_feed_gap_hours', 6)}h",
                        "next_allowed": blocked_until}), 409

    threading.Thread(target=run_feed, args=(angle, by),
                     kwargs={"force": force}, daemon=True).start()
    return jsonify({"success": True, "message": f"Feed started ({angle} deg)"})

@app.get("/api/log")
def get_log():
    limit = int(request.args.get("limit", 20))
    return jsonify(load_log()[-limit:])

@app.delete("/api/log")
def clear_log():
    LOG_FILE.write_text("[]")
    return jsonify({"success": True})


if __name__ == "__main__":
    print("=" * 52)
    print("  AquaFeed API — http://0.0.0.0:5000")
    print(f"  Auth token:  {TOKEN}")
    print("  (paste this token into the UI when adding the tank)")
    print("=" * 52)
    app.run(host="0.0.0.0", port=5000, debug=False)
