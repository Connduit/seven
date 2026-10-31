import sqlite3, os, time
DB_PATH = os.environ.get("DB_PATH", "influencers.db")

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS personas(
          id INTEGER PRIMARY KEY, name TEXT, handle TEXT, core TEXT, goal TEXT,
          personality TEXT, life TEXT, autonomy TEXT DEFAULT 'approve', paused INTEGER DEFAULT 0,
          ig_user_id TEXT DEFAULT '', ig_token TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS memories(
          id INTEGER PRIMARY KEY, persona_id INTEGER, kind TEXT, content TEXT, ts REAL);
        CREATE TABLE IF NOT EXISTS queue(
          id INTEGER PRIMARY KEY, persona_id INTEGER, content TEXT, status TEXT DEFAULT 'pending', ts REAL,
          image_prompt TEXT DEFAULT '', image_url TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS versions(
          id INTEGER PRIMARY KEY, persona_id INTEGER, personality TEXT, ts REAL);
        """)
        for t, col in [("personas", "ig_user_id TEXT DEFAULT ''"), ("personas", "ig_token TEXT DEFAULT ''"),
                       ("queue", "image_prompt TEXT DEFAULT ''"), ("queue", "image_url TEXT DEFAULT ''")]:
            try: c.execute(f"ALTER TABLE {t} ADD COLUMN {col}")
            except sqlite3.OperationalError: pass  # already exists

def q(sql, args=(), one=False):
    with conn() as c:
        rows = [dict(r) for r in c.execute(sql, args).fetchall()]
    return (rows[0] if rows else None) if one else rows

def run(sql, args=()):
    with conn() as c:
        return c.execute(sql, args).lastrowid

def now():
    return time.time()
