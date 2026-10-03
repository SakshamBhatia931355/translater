"""SQLite persistence for the local single-learner experience."""
from __future__ import annotations
import json, os, sqlite3, threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
_LOCK=threading.RLock(); _READY=set()

def database_path():
    path=Path(os.environ.get("JAPANESE_PRACTICE_DB",ROOT/"instance"/"japanese_practice.sqlite3")).expanduser().resolve()
    path.parent.mkdir(parents=True,exist_ok=True); return path

def connect():
    conn=sqlite3.connect(database_path(),timeout=10); conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON"); conn.execute("PRAGMA journal_mode=WAL"); return conn

@contextmanager
def db():
    conn=connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def now(): return datetime.now(timezone.utc)
def stamp(): return now().isoformat(timespec="seconds")

def initialize():
    path=str(database_path())
    with _LOCK:
        if path in _READY: return
        conn=connect()
        try:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS profile(id INTEGER PRIMARY KEY CHECK(id=1),display_name TEXT NOT NULL DEFAULT '',display_language TEXT NOT NULL DEFAULT 'en',jlpt_level TEXT NOT NULL DEFAULT 'N5',learning_goal TEXT NOT NULL DEFAULT 'general',daily_minutes INTEGER NOT NULL DEFAULT 10,hiragana_familiar INTEGER NOT NULL DEFAULT 0,katakana_familiar INTEGER NOT NULL DEFAULT 0,kanji_familiar INTEGER NOT NULL DEFAULT 0,practice_style TEXT NOT NULL DEFAULT 'balanced',onboarding_complete INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS vocabulary(id INTEGER PRIMARY KEY,word TEXT NOT NULL,reading TEXT NOT NULL,meaning TEXT NOT NULL,level TEXT NOT NULL,topic TEXT NOT NULL DEFAULT 'Basics',example_ja TEXT NOT NULL DEFAULT '',example_en TEXT NOT NULL DEFAULT '',custom INTEGER NOT NULL DEFAULT 0,bookmarked INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(word,level));
            CREATE TABLE IF NOT EXISTS reviews(vocabulary_id INTEGER PRIMARY KEY REFERENCES vocabulary(id) ON DELETE CASCADE,due_at TEXT NOT NULL,interval_days REAL NOT NULL DEFAULT 0,ease REAL NOT NULL DEFAULT 2.5,repetitions INTEGER NOT NULL DEFAULT 0,lapses INTEGER NOT NULL DEFAULT 0,last_reviewed TEXT);
            CREATE TABLE IF NOT EXISTS lesson_progress(lesson_id TEXT PRIMARY KEY,attempts INTEGER NOT NULL DEFAULT 0,best_score REAL NOT NULL DEFAULT 0,completed INTEGER NOT NULL DEFAULT 0,last_answers TEXT NOT NULL DEFAULT '{}',updated_at TEXT NOT NULL,completed_at TEXT);
            CREATE TABLE IF NOT EXISTS activity(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,duration_seconds INTEGER NOT NULL DEFAULT 0,details TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS activity_created_idx ON activity(created_at);
            CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,scenario_id TEXT NOT NULL,mode TEXT NOT NULL,turns INTEGER NOT NULL DEFAULT 0,completed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,messages TEXT NOT NULL DEFAULT '[]');
            CREATE TABLE IF NOT EXISTS study_timer(learner_session TEXT PRIMARY KEY,last_seen TEXT NOT NULL,elapsed_seconds INTEGER NOT NULL DEFAULT 0);
            INSERT OR IGNORE INTO profile(id,updated_at) VALUES(1,CURRENT_TIMESTAMP);
            """)
            _seed_vocabulary(conn); conn.commit(); _READY.add(path)
        finally: conn.close()

def _seed_vocabulary(conn):
    source=ROOT/"src"/"static"/"vocabulary.json"
    try: decks=json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError,json.JSONDecodeError): return
    ex={"水":("水をください。","Water, please."),"本":("本を読みます。","I read a book."),"学生":("私は学生です。","I am a student."),"駅":("駅はどこですか。","Where is the station?"),"学校":("学校へ行きます。","I go to school."),"食べる":("りんごを食べます。","I eat an apple."),"行く":("学校へ行きます。","I go to school."),"見る":("映画を見ます。","I watch a movie.")}
    for level,cards in decks.items():
        for card in cards:
            ja,en=ex.get(card["word"],("",""))
            conn.execute("INSERT OR IGNORE INTO vocabulary(word,reading,meaning,level,example_ja,example_en,created_at) VALUES(?,?,?,?,?,?,?)",(card["word"],card["reading"],card["meaning"],level,ja,en,stamp()))

def get_profile():
    initialize()
    with db() as c: return dict(c.execute("SELECT * FROM profile WHERE id=1").fetchone())

def save_profile(p):
    current=get_profile(); data={k:p.get(k,current[k]) for k in ("display_name","display_language","jlpt_level","learning_goal","daily_minutes","hiragana_familiar","katakana_familiar","kanji_familiar","practice_style")}
    data["display_name"]=str(data["display_name"]).strip()[:60]
    if str(data["display_language"])!="en": raise ValueError("English display language is currently available.")
    if str(data["jlpt_level"]) not in {"N5","N4","N3","N2","N1"}: raise ValueError("Choose a level from N5 to N1.")
    if str(data["learning_goal"]) not in {"conversation","travel","jlpt","reading","writing","general"}: raise ValueError("Choose a listed learning goal.")
    data["daily_minutes"]=int(data["daily_minutes"])
    if data["daily_minutes"] not in {5,10,15,20,30}: raise ValueError("Choose a 5, 10, 15, 20, or 30 minute target.")
    for k in ("hiragana_familiar","katakana_familiar","kanji_familiar"):
        data[k]=int(data[k])
        if data[k] not in {0,1,2}: raise ValueError("Script familiarity must be new, some, or comfortable.")
    if str(data["practice_style"]) not in {"balanced","speaking","reading","writing","structured"}: raise ValueError("Choose a listed practice style.")
    with db() as c:
        c.execute("UPDATE profile SET display_name=?,display_language=?,jlpt_level=?,learning_goal=?,daily_minutes=?,hiragana_familiar=?,katakana_familiar=?,kanji_familiar=?,practice_style=?,onboarding_complete=1,updated_at=? WHERE id=1",tuple(data[k] for k in ("display_name","display_language","jlpt_level","learning_goal","daily_minutes","hiragana_familiar","katakana_familiar","kanji_familiar","practice_style"))+(stamp(),))
        c.execute("INSERT INTO activity(kind,created_at) VALUES('preferences_saved',?)",(stamp(),))
    return get_profile()

def log_activity(kind,seconds=0,details=None):
    initialize(); body=json.dumps(details or {},ensure_ascii=False)[:2000]
    with db() as c: c.execute("INSERT INTO activity(kind,duration_seconds,details,created_at) VALUES(?,?,?,?)",(str(kind)[:40],min(7200,max(0,int(seconds))),body,stamp()))

def study_tick(session_key,seconds=30):
    initialize(); seconds=min(60,max(1,int(seconds))); t=now(); ts=t.isoformat(timespec="seconds"); credited=0
    with db() as c:
        row=c.execute("SELECT * FROM study_timer WHERE learner_session=?",(session_key,)).fetchone()
        if row is None:
            credited=seconds; c.execute("INSERT INTO study_timer VALUES(?,?,?)",(session_key,ts,credited))
        else:
            gap=(t-datetime.fromisoformat(row["last_seen"])).total_seconds()
            if 10<=gap<=120: credited=min(seconds,int(gap))
            elif gap>120: credited=seconds
            c.execute("UPDATE study_timer SET last_seen=?,elapsed_seconds=elapsed_seconds+? WHERE learner_session=?",(ts,credited,session_key))
        if credited: c.execute("INSERT INTO activity(kind,duration_seconds,created_at) VALUES('study_time',?,?)",(credited,ts))
    return {"credited_seconds":credited}

def dashboard():
    p=get_profile(); today=date.today().isoformat(); prev=(date.today()-timedelta(days=1)).isoformat()
    with db() as c:
        rows=c.execute("SELECT substr(created_at,1,10) day,SUM(duration_seconds) seconds,COUNT(*) events FROM activity WHERE kind IN ('study_time','lesson_completed','lesson_attempt','vocabulary_review','translation','recognition','conversation_turn','conversation_completed') GROUP BY day").fetchall()
        days={r["day"]:{"seconds":r["seconds"] or 0,"events":r["events"]} for r in rows}
        streak=0; cursor=date.fromisoformat(today if today in days else prev)
        while cursor.isoformat() in days: streak+=1; cursor-=timedelta(days=1)
        week=[{"date":d,"minutes":round(days.get(d,{}).get("seconds",0)/60,1),"events":days.get(d,{}).get("events",0)} for d in ((date.today()-timedelta(days=i)).isoformat() for i in range(6,-1,-1))]
        completed=c.execute("SELECT COUNT(*) FROM lesson_progress WHERE completed=1").fetchone()[0]
        mastered=c.execute("SELECT COUNT(*) FROM reviews WHERE repetitions>=5 AND interval_days>=21").fetchone()[0]
        due=c.execute("SELECT COUNT(*) FROM vocabulary v LEFT JOIN reviews r ON r.vocabulary_id=v.id WHERE r.vocabulary_id IS NULL OR r.due_at<=?",(stamp(),)).fetchone()[0]
        reviewed=c.execute("SELECT COUNT(*) FROM reviews WHERE last_reviewed IS NOT NULL").fetchone()[0]
        sessions=c.execute("SELECT COUNT(*) FROM conversations WHERE turns>0").fetchone()[0]
        recent=[dict(r) for r in c.execute("SELECT kind,details,created_at FROM activity ORDER BY id DESC LIMIT 8")]
    for item in recent:
        try: item["details"]=json.loads(item["details"])
        except json.JSONDecodeError: item["details"]={}
    secs=days.get(today,{}).get("seconds",0)
    return {"profile":p,"today_minutes":round(secs/60,1),"today_goal_minutes":p["daily_minutes"],"goal_complete":secs>=p["daily_minutes"]*60,"streak_days":streak,"total_study_minutes":round(sum(x["seconds"] for x in days.values())/60,1),"lessons_completed":completed,"vocabulary_mastered":mastered,"vocabulary_reviewed":reviewed,"vocabulary_due":due,"conversation_sessions":sessions,"week":week,"recent_activity":recent}

def lesson_statuses():
    initialize()
    with db() as c: rows=c.execute("SELECT * FROM lesson_progress").fetchall()
    return {r["lesson_id"]:{"attempts":r["attempts"],"best_score":r["best_score"],"completed":bool(r["completed"]),"updated_at":r["updated_at"]} for r in rows}

def save_lesson_attempt(lesson_id,answers,score,seconds=0):
    initialize(); ts=stamp(); passed=score>=0.6; body=json.dumps(answers,ensure_ascii=False)[:4000]
    with db() as c:
        old=c.execute("SELECT * FROM lesson_progress WHERE lesson_id=?",(lesson_id,)).fetchone()
        best=max(score,old["best_score"] if old else 0); completed=int(passed or bool(old and old["completed"]))
        completed_at=(old["completed_at"] if old else None) or (ts if completed else None)
        c.execute("""INSERT INTO lesson_progress(lesson_id,attempts,best_score,completed,last_answers,updated_at,completed_at) VALUES(?,1,?,?,?,?,?)
        ON CONFLICT(lesson_id) DO UPDATE SET attempts=attempts+1,best_score=MAX(best_score,excluded.best_score),completed=MAX(completed,excluded.completed),last_answers=excluded.last_answers,updated_at=excluded.updated_at,completed_at=COALESCE(completed_at,excluded.completed_at)""",(lesson_id,best,completed,body,ts,completed_at))
    log_activity("lesson_completed" if passed else "lesson_attempt",0,{"lesson_id":lesson_id,"score":round(score,3)})
    return {**lesson_statuses()[lesson_id],"passed":passed,"score":round(score,3)}

def vocabulary(level=None):
    initialize(); q="SELECT v.*,r.due_at,r.interval_days,r.repetitions,r.lapses,r.last_reviewed,CASE WHEN r.repetitions>=5 AND r.interval_days>=21 THEN 1 ELSE 0 END mastered FROM vocabulary v LEFT JOIN reviews r ON r.vocabulary_id=v.id"; args=[]
    if level in {"N5","N4","N3","N2","N1"}: q+=" WHERE v.level=?"; args.append(level)
    q+=" ORDER BY v.level,v.id"
    with db() as c: return [dict(r) for r in c.execute(q,args).fetchall()]

def due_vocabulary(level=None,limit=20):
    t=stamp(); return [v for v in vocabulary(level) if not v["due_at"] or v["due_at"]<=t][:max(1,min(50,int(limit)))]

def review_vocabulary(vocab_id,rating):
    initialize()
    if rating not in {"again","hard","good","easy"}: raise ValueError("Choose Again, Hard, Good, or Easy.")
    t=now(); ts=t.isoformat(timespec="seconds")
    with db() as c:
        card=c.execute("SELECT * FROM vocabulary WHERE id=?",(int(vocab_id),)).fetchone()
        if not card: raise LookupError("Vocabulary card not found.")
        old=c.execute("SELECT * FROM reviews WHERE vocabulary_id=?",(int(vocab_id),)).fetchone(); reps=old["repetitions"] if old else 0; lapses=old["lapses"] if old else 0; ease=old["ease"] if old else 2.5; days=old["interval_days"] if old else 0
        if rating=="again": reps=0; lapses+=1; days=0; due=t+timedelta(minutes=10)
        elif rating=="hard": reps+=1; ease=max(1.3,ease-.15); days=max(1,days*1.2 if days else 1); due=t+timedelta(days=days)
        elif rating=="good": reps+=1; days=1 if reps==1 else (3 if reps==2 else max(1,days*ease)); due=t+timedelta(days=days)
        else: reps+=1; ease+=.15; days=2 if reps==1 else max(2,days*ease*1.3); due=t+timedelta(days=days)
        c.execute("""INSERT INTO reviews VALUES(?,?,?,?,?,?,?) ON CONFLICT(vocabulary_id) DO UPDATE SET due_at=excluded.due_at,interval_days=excluded.interval_days,ease=excluded.ease,repetitions=excluded.repetitions,lapses=excluded.lapses,last_reviewed=excluded.last_reviewed""",(int(vocab_id),due.isoformat(timespec="seconds"),round(days,2),round(ease,2),reps,lapses,ts))
    log_activity("vocabulary_review",20,{"vocabulary_id":int(vocab_id),"rating":rating,"level":card["level"]})
    return {"vocabulary_id":int(vocab_id),"rating":rating,"repetitions":reps,"interval_days":round(days,2),"due_at":due.isoformat(timespec="seconds"),"mastered":reps>=5 and days>=21}

def add_custom_vocabulary(p):
    initialize(); word=str(p.get("word","")).strip()[:80]; reading=str(p.get("reading","")).strip()[:100]; meaning=str(p.get("meaning","")).strip()[:180]; level=str(p.get("level","N5"))
    if not word or not reading or not meaning: raise ValueError("Word, reading, and meaning are required.")
    if level not in {"N5","N4","N3","N2","N1"}: raise ValueError("Choose a level from N5 to N1.")
    with db() as c:
        try: cur=c.execute("INSERT INTO vocabulary(word,reading,meaning,level,topic,example_ja,example_en,custom,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(word,reading,meaning,level,str(p.get("topic","My words"))[:40],str(p.get("example_ja",""))[:150],str(p.get("example_en",""))[:200],1,stamp()))
        except sqlite3.IntegrityError: raise ValueError("That word already exists in this level.") from None
        card_id=cur.lastrowid
    log_activity("vocabulary_added",0,{"vocabulary_id":card_id,"level":level}); return next(v for v in vocabulary(level) if v["id"]==card_id)

def bookmark_vocabulary(vocab_id):
    initialize()
    with db() as c:
        row=c.execute("SELECT bookmarked FROM vocabulary WHERE id=?",(int(vocab_id),)).fetchone()
        if not row: raise LookupError("Vocabulary card not found.")
        value=1-int(row[0]); c.execute("UPDATE vocabulary SET bookmarked=? WHERE id=?",(value,int(vocab_id)))
    log_activity("vocabulary_bookmark",0,{"vocabulary_id":int(vocab_id),"bookmarked":bool(value)}); return {"vocabulary_id":int(vocab_id),"bookmarked":bool(value)}

def export_progress():
    initialize(); data={}
    with db() as c:
        for table in ("profile","vocabulary","reviews","lesson_progress","activity","conversations"):
            data[table]=[dict(r) for r in c.execute(f"SELECT * FROM {table}").fetchall()]
    return {"format":"japanese-practice-export-v1","exported_at":stamp(),"data":data}
