"""Rugas Queue Management — FastAPI + SQLite backend.

Features (per assignment brief):
  1. Manager login, create queues
  2. Named queues
  3. Add persons -> token auto-created
  4. List waiting tokens
  5. Move tokens up / down
  6. Assign top token for service (button click)
  7. Cancel a token
  8. Dashboard analytics: wait times, queue lengths, trends

Run:  uvicorn main:app --reload --port 8000
Login:  manager / rugas123  (seeded on first run; change in README)
"""
import hashlib
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "queue.db")
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="Rugas Queue Management")

# ---------------------------------------------------------------- db helpers
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS managers (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                manager_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                prefix TEXT NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_id INTEGER NOT NULL REFERENCES queues(id) ON DELETE CASCADE,
                token_no TEXT NOT NULL,
                person_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'waiting',
                position INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                served_at INTEGER,
                done_at INTEGER
            );
            """
        )
        row = c.execute("SELECT id FROM managers WHERE username = 'manager'").fetchone()
        if not row:
            pw = hashlib.sha256("rugas123".encode()).hexdigest()
            c.execute(
                "INSERT INTO managers (username, password_hash) VALUES ('manager', ?)",
                (pw,),
            )


def now_ts() -> int:
    return int(time.time())


def fmt_ts(ts):
    if not ts:
        return None
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Kolkata")
    except Exception:
        tz = timezone.utc
    return datetime.fromtimestamp(ts, tz=tz).isoformat()


def token_to_dict(r):
    return {
        "id": r["id"],
        "queue_id": r["queue_id"],
        "token_no": r["token_no"],
        "person_name": r["person_name"],
        "status": r["status"],
        "position": r["position"],
        "created_at": fmt_ts(r["created_at"]),
        "served_at": fmt_ts(r["served_at"]),
        "done_at": fmt_ts(r["done_at"]),
        "wait_seconds": (r["served_at"] or now_ts()) - r["created_at"]
        if r["status"] in ("waiting", "serving")
        else ((r["served_at"] or r["done_at"] or r["created_at"]) - r["created_at"]),
    }


def queue_to_dict(r, with_tokens=False, conn=None):
    d = {
        "id": r["id"],
        "name": r["name"],
        "prefix": r["prefix"],
        "created_at": fmt_ts(r["created_at"]),
    }
    if with_tokens and conn is not None:
        rows = conn.execute(
            "SELECT * FROM tokens WHERE queue_id = ? AND status IN ('waiting','serving') "
            "ORDER BY position ASC",
            (r["id"],),
        ).fetchall()
        d["tokens"] = [token_to_dict(t) for t in rows]
        d["waiting_count"] = sum(1 for t in rows if t["status"] == "waiting")
        d["serving"] = next(
            (token_to_dict(t) for t in rows if t["status"] == "serving"), None
        )
    return d


# ---------------------------------------------------------------- auth
def require_auth(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Login required")
    token = authorization[7:]
    with db() as c:
        row = c.execute("SELECT manager_id FROM sessions WHERE token = ?", (token,)).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid session")
    return row["manager_id"]


class LoginIn(BaseModel):
    username: str
    password: str


@app.post("/api/login")
def login(body: LoginIn):
    pw = hashlib.sha256(body.password.encode()).hexdigest()
    with db() as c:
        row = c.execute(
            "SELECT id FROM managers WHERE username = ? AND password_hash = ?",
            (body.username, pw),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Wrong username or password")
        token = secrets.token_hex(24)
        c.execute(
            "INSERT INTO sessions (token, manager_id, created_at) VALUES (?, ?, ?)",
            (token, row["id"], now_ts()),
        )
    return {"token": token, "manager": body.username}


@app.post("/api/logout")
def logout(authorization: str = Header(default="")):
    if authorization.startswith("Bearer "):
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token = ?", (authorization[7:],))
    return {"ok": True}


# ---------------------------------------------------------------- queues
class QueueIn(BaseModel):
    name: str


@app.get("/api/queues")
def list_queues(_=Depends(require_auth)):
    with db() as c:
        rows = c.execute("SELECT * FROM queues ORDER BY created_at ASC").fetchall()
        return [queue_to_dict(r, with_tokens=True, conn=c) for r in rows]


@app.post("/api/queues")
def create_queue(body: QueueIn, _=Depends(require_auth)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Queue name is required")
    prefix = "".join(ch for ch in name.upper() if ch.isalpha())[:1] or "Q"
    with db() as c:
        cur = c.execute(
            "INSERT INTO queues (name, prefix, created_at) VALUES (?, ?, ?)",
            (name, prefix, now_ts()),
        )
        row = c.execute("SELECT * FROM queues WHERE id = ?", (cur.lastrowid,)).fetchone()
        return queue_to_dict(row, with_tokens=True, conn=c)


@app.delete("/api/queues/{queue_id}")
def delete_queue(queue_id: int, _=Depends(require_auth)):
    with db() as c:
        cur = c.execute("DELETE FROM queues WHERE id = ?", (queue_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Queue not found")
    return {"ok": True}


# ---------------------------------------------------------------- tokens
class TokenIn(BaseModel):
    person_name: str


@app.post("/api/queues/{queue_id}/tokens")
def add_token(queue_id: int, body: TokenIn, _=Depends(require_auth)):
    name = body.person_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Person name is required")
    with db() as c:
        q = c.execute("SELECT * FROM queues WHERE id = ?", (queue_id,)).fetchone()
        if not q:
            raise HTTPException(status_code=404, detail="Queue not found")
        count = c.execute(
            "SELECT COUNT(*) FROM tokens WHERE queue_id = ?", (queue_id,)
        ).fetchone()[0]
        token_no = f"{q['prefix']}-{count + 1:03d}"
        pos = c.execute(
            "SELECT COALESCE(MAX(position), 0) FROM tokens "
            "WHERE queue_id = ? AND status IN ('waiting','serving')",
            (queue_id,),
        ).fetchone()[0] + 1
        cur = c.execute(
            "INSERT INTO tokens (queue_id, token_no, person_name, status, position, created_at) "
            "VALUES (?, ?, ?, 'waiting', ?, ?)",
            (queue_id, token_no, name, pos, now_ts()),
        )
        row = c.execute("SELECT * FROM tokens WHERE id = ?", (cur.lastrowid,)).fetchone()
        return token_to_dict(row)


def _waiting(conn, queue_id):
    return conn.execute(
        "SELECT * FROM tokens WHERE queue_id = ? AND status = 'waiting' ORDER BY position ASC",
        (queue_id,),
    ).fetchall()


def _renumber(conn, queue_id):
    rows = conn.execute(
        "SELECT id FROM tokens WHERE queue_id = ? AND status IN ('waiting','serving') "
        "ORDER BY position ASC",
        (queue_id,),
    ).fetchall()
    for i, r in enumerate(rows, start=1):
        conn.execute("UPDATE tokens SET position = ? WHERE id = ?", (i, r["id"]))


@app.post("/api/tokens/{token_id}/move")
def move_token(token_id: int, body: dict, _=Depends(require_auth)):
    direction = body.get("direction")
    if direction not in ("up", "down"):
        raise HTTPException(status_code=400, detail="direction must be 'up' or 'down'")
    with db() as c:
        t = c.execute("SELECT * FROM tokens WHERE id = ?", (token_id,)).fetchone()
        if not t or t["status"] != "waiting":
            raise HTTPException(status_code=404, detail="Waiting token not found")
        rows = _waiting(c, t["queue_id"])
        idx = next((i for i, r in enumerate(rows) if r["id"] == token_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail="Token not in queue")
        swap = idx - 1 if direction == "up" else idx + 1
        if swap < 0 or swap >= len(rows):
            return {"ok": True, "moved": False}
        a, b = rows[idx], rows[swap]
        c.execute("UPDATE tokens SET position = ? WHERE id = ?", (b["position"], a["id"]))
        c.execute("UPDATE tokens SET position = ? WHERE id = ?", (a["position"], b["id"]))
    return {"ok": True, "moved": True}


@app.post("/api/queues/{queue_id}/call-next")
def call_next(queue_id: int, _=Depends(require_auth)):
    with db() as c:
        q = c.execute("SELECT * FROM queues WHERE id = ?", (queue_id,)).fetchone()
        if not q:
            raise HTTPException(status_code=404, detail="Queue not found")
        current = c.execute(
            "SELECT * FROM tokens WHERE queue_id = ? AND status = 'serving'",
            (queue_id,),
        ).fetchone()
        if current:
            raise HTTPException(
                status_code=400,
                detail=f"{current['token_no']} is already being served. Complete it first.",
            )
        rows = _waiting(c, queue_id)
        if not rows:
            raise HTTPException(status_code=400, detail="No one is waiting in this queue")
        top = rows[0]
        c.execute(
            "UPDATE tokens SET status = 'serving', served_at = ? WHERE id = ?",
            (now_ts(), top["id"]),
        )
        row = c.execute("SELECT * FROM tokens WHERE id = ?", (top["id"],)).fetchone()
        return token_to_dict(row)


@app.post("/api/tokens/{token_id}/complete")
def complete_token(token_id: int, _=Depends(require_auth)):
    with db() as c:
        t = c.execute("SELECT * FROM tokens WHERE id = ?", (token_id,)).fetchone()
        if not t or t["status"] != "serving":
            raise HTTPException(status_code=404, detail="Serving token not found")
        c.execute(
            "UPDATE tokens SET status = 'done', done_at = ? WHERE id = ?",
            (now_ts(), token_id),
        )
        _renumber(c, t["queue_id"])
    return {"ok": True}


@app.post("/api/tokens/{token_id}/cancel")
def cancel_token(token_id: int, _=Depends(require_auth)):
    with db() as c:
        t = c.execute("SELECT * FROM tokens WHERE id = ?", (token_id,)).fetchone()
        if not t or t["status"] not in ("waiting", "serving"):
            raise HTTPException(status_code=404, detail="Active token not found")
        c.execute(
            "UPDATE tokens SET status = 'cancelled', done_at = ? WHERE id = ?",
            (now_ts(), token_id),
        )
        _renumber(c, t["queue_id"])
    return {"ok": True}


# ---------------------------------------------------------------- dashboard
@app.get("/api/dashboard")
def dashboard(_=Depends(require_auth)):
    with db() as c:
        queues = c.execute("SELECT * FROM queues ORDER BY created_at ASC").fetchall()
        per_queue = []
        total_waiting = total_serving = total_done = total_cancelled = 0
        waits = []
        for q in queues:
            w = c.execute(
                "SELECT COUNT(*) FROM tokens WHERE queue_id = ? AND status = 'waiting'",
                (q["id"],),
            ).fetchone()[0]
            s = c.execute(
                "SELECT COUNT(*) FROM tokens WHERE queue_id = ? AND status = 'serving'",
                (q["id"],),
            ).fetchone()[0]
            d = c.execute(
                "SELECT COUNT(*) FROM tokens WHERE queue_id = ? AND status = 'done'",
                (q["id"],),
            ).fetchone()[0]
            x = c.execute(
                "SELECT COUNT(*) FROM tokens WHERE queue_id = ? AND status = 'cancelled'",
                (q["id"],),
            ).fetchone()[0]
            total_waiting += w
            total_serving += s
            total_done += d
            total_cancelled += x
            served = c.execute(
                "SELECT created_at, served_at FROM tokens "
                "WHERE queue_id = ? AND served_at IS NOT NULL",
                (q["id"],),
            ).fetchall()
            waits += [r["served_at"] - r["created_at"] for r in served]
            per_queue.append(
                {"id": q["id"], "name": q["name"], "waiting": w,
                 "serving": s, "served": d, "cancelled": x}
            )
        # wait-time trend: tokens created per hour, last 8 hours (UTC hours labelled local)
        now = now_ts()
        trend = []
        for h in range(7, -1, -1):
            start = now - (h + 1) * 3600
            end = now - h * 3600
            n = c.execute(
                "SELECT COUNT(*) FROM tokens WHERE created_at >= ? AND created_at < ?",
                (start, end),
            ).fetchone()[0]
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo("Asia/Kolkata")
            except Exception:
                tz = timezone.utc
            label = datetime.fromtimestamp(end, tz=tz).strftime("%I %p")
            trend.append({"hour": label, "tokens": n})
        longest = c.execute(
            "SELECT token_no, person_name, created_at FROM tokens WHERE status = 'waiting' "
            "ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        avg_wait = round(sum(waits) / len(waits)) if waits else 0
        return {
            "total_waiting": total_waiting,
            "total_serving": total_serving,
            "total_served": total_done,
            "total_cancelled": total_cancelled,
            "avg_wait_seconds": avg_wait,
            "longest_waiting": (
                {
                    "token_no": longest["token_no"],
                    "person_name": longest["person_name"],
                    "wait_seconds": now - longest["created_at"],
                }
                if longest
                else None
            ),
            "per_queue": per_queue,
            "trend": trend,
        }


# ---------------------------------------------------------------- frontend
@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def startup():
    init_db()
    # seed two demo queues on a totally fresh DB so the first screen is not empty
    with db() as c:
        n = c.execute("SELECT COUNT(*) FROM queues").fetchone()[0]
        if n == 0:
            t = now_ts()
            c.execute(
                "INSERT INTO queues (name, prefix, created_at) VALUES ('Billing', 'B', ?)",
                (t,),
            )
            c.execute(
                "INSERT INTO queues (name, prefix, created_at) VALUES ('Support', 'S', ?)",
                (t,),
            )


if __name__ == "__main__":
    import uvicorn

    init_db()
    uvicorn.run(app, host="127.0.0.1", port=8000)
