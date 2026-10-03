"""Flask web app and API for Japanese Practice."""
import argparse, hashlib, hmac, io, json, os, secrets, sys, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from PIL import Image, ImageOps, UnidentifiedImageError

SRC_DIR=Path(__file__).resolve().parent
ROOT=SRC_DIR.parent
if str(SRC_DIR) not in sys.path: sys.path.insert(0,str(SRC_DIR))
from predict import predict_line
from translation import translate_japanese
import learning_store as store
from learning_store import kana_to_romaji
from learning_content import LESSONS, SCENARIOS
from conversation_provider import ProviderUnavailable, generate_tutor_turn, tutor_configured


def _secret_key():
    configured=os.environ.get("PRACTICE_SECRET_KEY","").strip()
    if configured: return configured
    folder=ROOT/"instance"; folder.mkdir(parents=True,exist_ok=True); path=folder/"session.key"
    try:
        with path.open("xb") as out: out.write(secrets.token_urlsafe(48).encode("ascii"))
    except FileExistsError: pass
    return path.read_text(encoding="ascii").strip()

app=Flask(__name__)
app.config.update(SECRET_KEY=_secret_key(),MAX_CONTENT_LENGTH=12*1024*1024,
    SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE="Lax",PERMANENT_SESSION_LIFETIME=60*60*24*30)
ACCESS_CODE=""
_LOGIN_FAILURES={}
_LOGIN_FAILURES_LOCK=__import__("threading").Lock()
LESSON_MAP={item["id"]:item for item in LESSONS}
SCENARIO_MAP={item["id"]:item for item in SCENARIOS}

@app.before_request
def require_public_access_code():
    if not ACCESS_CODE or request.endpoint in {"login","health","static"}: return None
    supplied=request.headers.get("X-Sakura-Access-Code","")
    if hmac.compare_digest(supplied,ACCESS_CODE) or session.get("practice_authorized"): return None
    if request.path.startswith("/api/"): return jsonify(error="Enter the access code shown on the PC."),401
    return redirect(url_for("login",next=request.path))

@app.before_request
def ensure_database():
    store.initialize()

@app.errorhandler(413)
def too_large(_error):
    if request.path.startswith("/api/"): return jsonify(error="Upload is too large. Choose an image smaller than 12 MB."),413
    return "Upload is too large. Choose an image smaller than 12 MB.",413

@app.route("/login",methods=["GET","POST"])
def login():
    message=""
    token=session.get("login_csrf")
    if not token:
        token=secrets.token_urlsafe(32); session["login_csrf"]=token
    if request.method=="POST":
        submitted_token=request.form.get("csrf_token","")
        if not hmac.compare_digest(submitted_token,token):
            return render_template("login.html",message="This sign-in form expired. Reload and try again.",csrf_token=token),400
        # Keep only a keyed digest of the client address; cap retries without
        # retaining raw IP addresses or writing them to application logs.
        client_key=hashlib.sha256((request.remote_addr or "unknown").encode("utf-8")).hexdigest()
        now=time.monotonic()
        with _LOGIN_FAILURES_LOCK:
            recent=[t for t in _LOGIN_FAILURES.get(client_key,[]) if now-t<600]
            _LOGIN_FAILURES[client_key]=recent
            if len(recent)>=10:
                return render_template("login.html",message="Too many attempts. Wait ten minutes and try again.",csrf_token=token),429
        submitted=request.form.get("code","")
        if ACCESS_CODE and hmac.compare_digest(submitted,ACCESS_CODE):
            session.clear(); session["practice_authorized"]=True; session.permanent=True
            dest=request.args.get("next","/")
            if not dest.startswith("/") or dest.startswith("//"): dest="/"
            return redirect(dest)
        with _LOGIN_FAILURES_LOCK:
            _LOGIN_FAILURES[client_key].append(now)
        message="That access code did not match. Try again."
    return render_template("login.html",message=message,csrf_token=token)

@app.get("/health")
def health(): return jsonify(ok=True,access_code_required=bool(ACCESS_CODE))

@app.get("/")
def index(): return render_template("mobile.html")

@app.get("/service-worker.js")
def service_worker():
    response=send_from_directory(SRC_DIR/"static","service-worker.js",mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"]="/"
    response.headers["Cache-Control"]="no-cache"
    return response

@app.post("/api/recognize")
def recognize():
    photo=request.files.get("image")
    if not photo or not photo.filename: return jsonify(error="Choose or take a photo first."),400
    try:
        with Image.open(io.BytesIO(photo.read())) as source: image=ImageOps.exif_transpose(source).convert("RGB")
        readings=predict_line(image)
    except (UnidentifiedImageError,OSError,ValueError) as exc: return jsonify(error=f"Could not read that image: {exc}"),400
    store.log_activity("recognition",0,{"characters":len(readings)})
    return jsonify(kana="".join(x["kana"] for x in readings),readings=[{
        "kana":x["kana"],"pronunciation":x["label"].lower(),"confidence":round(x["confidence"],4),
        "alternatives":[{"kana":a[1],"pronunciation":a[0].lower(),"confidence":round(a[2],4)} for a in x["alternatives"]]
    } for x in readings])

@app.post("/api/translate")
def translate():
    payload=request.get_json(silent=True) or {}; text=" ".join(str(payload.get("text","")).split())
    if not text: return jsonify(error="Enter Japanese text to translate."),400
    if len(text)>2000: return jsonify(error="Translate up to 2,000 characters at a time."),400
    try: translated=translate_japanese(text)
    except (FileNotFoundError,OSError,RuntimeError) as exc: return jsonify(error=str(exc)),503
    store.log_activity("translation",0,{"characters":len(text)})
    store.save_translation(text,translated)
    return jsonify(translation=translated)

@app.get("/api/v1/capabilities")
def capabilities():
    return jsonify(tutor_mode="ai" if tutor_configured() else "guided",ai_configured=tutor_configured(),
        handwriting_scripts=["hiragana"],translation_scripts=["hiragana","katakana","kanji","mixed Japanese"],
        speech_recognition="browser capability; platform support varies",pronunciation_scoring=False,
        persistence="local SQLite single-learner profile")

@app.get("/api/v1/profile")
def profile_get(): return jsonify(store.get_profile())

@app.put("/api/v1/profile")
def profile_put():
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return jsonify(error="Send profile settings as a JSON object."),400
    try: return jsonify(store.save_profile(payload))
    except (ValueError,TypeError) as exc: return jsonify(error=str(exc)),400

@app.get("/api/v1/dashboard")
def dashboard(): return jsonify(store.dashboard())

@app.get("/api/v1/translations")
def translation_history(): return jsonify(items=store.translation_history())

@app.post("/api/v1/phrases")
def phrase_save():
    payload=request.get_json(silent=True) or {}
    try: return jsonify(item=store.save_phrase(payload.get("text",""),payload.get("translation",""),payload.get("label",""))),201
    except ValueError as exc: return jsonify(error=str(exc)),400

@app.get("/api/v1/phrases")
def phrases_list(): return jsonify(items=store.list_saved_phrases())

@app.delete("/api/v1/phrases/<int:phrase_id>")
def phrase_delete(phrase_id):
    if not store.delete_saved_phrase(phrase_id): return jsonify(error="Saved phrase not found."),404
    return jsonify(ok=True)

@app.post("/api/v1/writing")
def writing_save():
    payload=request.get_json(silent=True) or {}
    if not isinstance(payload.get("strokes",[]),list): return jsonify(error="Drawing strokes must be a list."),400
    try: attempt_id=store.save_writing_attempt(payload.get("prompt",""),payload.get("predicted",""),payload.get("confidence",0),payload.get("strokes",[]))
    except (ValueError,TypeError) as exc: return jsonify(error=str(exc)),400
    return jsonify(id=attempt_id),201

@app.get("/api/v1/writing")
def writing_list(): return jsonify(items=store.writing_history())

@app.post("/api/v1/study/tick")
def study_tick():
    learner=session.get("learner_session")
    if not learner: learner=secrets.token_urlsafe(24); session["learner_session"]=learner
    payload=request.get_json(silent=True) or {}
    try: return jsonify(store.study_tick(learner,payload.get("seconds",30)))
    except (ValueError,TypeError) as exc: return jsonify(error=str(exc)),400

@app.get("/api/v1/lessons")
def lessons_list():
    status=store.lesson_statuses(); level=request.args.get("level")
    data=[{**lesson_payload(item),"progress":status.get(item["id"],{"attempts":0,"best_score":0,"completed":False})} for item in LESSONS if not level or item["level"]==level]
    return jsonify(lessons=data,source_note="Curated starter content; not official JLPT course material.")

def lesson_payload(lesson):
    return {**lesson,"examples":[{**example,"romaji":example.get("romaji") or kana_to_romaji(example.get("reading",""))} for example in lesson["examples"]]}

@app.get("/api/v1/lessons/<lesson_id>")
def lesson_get(lesson_id):
    lesson=LESSON_MAP.get(lesson_id)
    if not lesson: return jsonify(error="Lesson not found."),404
    return jsonify(lesson=lesson_payload(lesson),progress=store.lesson_statuses().get(lesson_id,{"attempts":0,"best_score":0,"completed":False}))

@app.post("/api/v1/lessons/<lesson_id>/complete")
def lesson_complete(lesson_id):
    lesson=LESSON_MAP.get(lesson_id)
    if not lesson: return jsonify(error="Lesson not found."),404
    payload=request.get_json(silent=True) or {}; answers=payload.get("answers",{})
    if not isinstance(answers,dict): return jsonify(error="Answers must be a JSON object."),400
    exercise=lesson["exercise"]; submitted=str(answers.get("answer","")).strip().casefold(); correct=submitted==exercise["answer"].strip().casefold()
    try: result=store.save_lesson_attempt(lesson_id,answers,1.0 if correct else 0.0)
    except (ValueError,TypeError) as exc: return jsonify(error="Invalid lesson duration."),400
    return jsonify(**result,answer=exercise["answer"],explanation=exercise["explanation"])

@app.get("/api/v1/vocabulary")
def vocabulary_list():
    level=request.args.get("level"); cards=store.vocabulary(level)
    return jsonify(cards=cards,source_note="Starter and learner-created cards, not a complete official JLPT list.")

@app.get("/api/v1/reviews/due")
def vocabulary_due():
    level=request.args.get("level")
    try: return jsonify(cards=store.due_vocabulary(level,request.args.get("limit",20)))
    except (ValueError,TypeError): return jsonify(error="Limit must be a number.") ,400

@app.post("/api/v1/reviews/<int:vocabulary_id>")
def vocabulary_review(vocabulary_id):
    payload=request.get_json(silent=True) or {}
    try: return jsonify(store.review_vocabulary(vocabulary_id,str(payload.get("rating",""))))
    except LookupError as exc: return jsonify(error=str(exc)),404
    except ValueError as exc: return jsonify(error=str(exc)),400

@app.post("/api/v1/vocabulary/quiz")
def vocabulary_quiz():
    payload=request.get_json(silent=True) or {}
    if not isinstance(payload.get("correct"),bool): return jsonify(error="Quiz result must be true or false."),400
    try: vocabulary_id=int(payload.get("vocabulary_id"))
    except (TypeError,ValueError): return jsonify(error="Choose a vocabulary card."),400
    with store.db() as c: card=c.execute("SELECT id FROM vocabulary WHERE id=?",(vocabulary_id,)).fetchone()
    if not card: return jsonify(error="Vocabulary card not found."),404
    store.log_vocabulary_quiz(payload["correct"],vocabulary_id)
    return jsonify(saved=True)

@app.post("/api/v1/vocabulary")
def vocabulary_add():
    payload=request.get_json(silent=True)
    if not isinstance(payload,dict): return jsonify(error="Send a vocabulary object."),400
    try: return jsonify(card=store.add_custom_vocabulary(payload)),201
    except ValueError as exc: return jsonify(error=str(exc)),400

@app.post("/api/v1/vocabulary/<int:vocabulary_id>/bookmark")
def vocabulary_bookmark(vocabulary_id):
    try: return jsonify(store.bookmark_vocabulary(vocabulary_id))
    except LookupError as exc: return jsonify(error=str(exc)),404

@app.get("/api/v1/progress")
def progress(): return jsonify(store.dashboard())

@app.get("/api/v1/export")
def export_data():
    response=jsonify(store.export_progress()); response.headers["Content-Disposition"]="attachment; filename=japanese-practice-export.json"; return response

@app.delete("/api/v1/account/data")
def delete_local_data():
    # Retain schema and vocabulary, but remove learner content and reset preferences.
    with store.db() as c:
        for table in ("activity","lesson_progress","reviews","conversations","study_timer","translation_history","saved_phrases","writing_attempts"): c.execute("DELETE FROM "+table)
        c.execute("DELETE FROM vocabulary WHERE custom=1")
        c.execute("UPDATE vocabulary SET bookmarked=0")
        c.execute("UPDATE profile SET display_name='',display_language='en',jlpt_level='N5',learning_goal='general',daily_minutes=10,hiragana_familiar=0,katakana_familiar=0,kanji_familiar=0,practice_style='balanced',furigana_enabled=1,romaji_enabled=0,audio_speed=1.0,theme='light',onboarding_complete=0,updated_at=? WHERE id=1",(store.stamp(),))
    session.clear(); return jsonify(ok=True)

@app.get("/api/v1/conversations/scenarios")
def scenarios():
    return jsonify(mode="ai" if tutor_configured() else "guided",scenarios=[{k:v for k,v in s.items() if k!="turns"} for s in SCENARIOS])

@app.post("/api/v1/conversations")
def conversation_start():
    payload=request.get_json(silent=True) or {}; scenario=SCENARIO_MAP.get(str(payload.get("scenario_id","")))
    if not scenario: return jsonify(error="Choose a supported practice scenario."),400
    requested=str(payload.get("mode","ai")).lower()
    mode="ai" if requested!="guided" and tutor_configured() else "guided"; cid=str(uuid.uuid4()); ts=store.stamp(); opening=scenario["turns"][0]
    initial={"speaker":"assistant","text":opening["ja"],"translation":opening["en"],"created_at":ts}
    with store.db() as c: c.execute("INSERT INTO conversations(id,scenario_id,mode,created_at,updated_at,messages) VALUES(?,?,?,?,?,?)",(cid,scenario["id"],mode,ts,ts,json.dumps([initial],ensure_ascii=False)))
    return jsonify(id=cid,scenario=scenario,mode=mode,notice=("AI tutor enabled. Responses use the configured server-side provider." if mode=="ai" else "Guided mode: scripted prompts and suggested replies. No live AI or free-text evaluation is configured."),message=initial,suggestions=opening["suggestions"])

@app.get("/api/v1/conversations/<conversation_id>")
def conversation_get(conversation_id):
    with store.db() as c: row=c.execute("SELECT * FROM conversations WHERE id=?",(conversation_id,)).fetchone()
    if not row: return jsonify(error="Practice session not found."),404
    scenario=SCENARIO_MAP.get(row["scenario_id"])
    if not scenario: return jsonify(error="Practice scenario is no longer available."),404
    messages=json.loads(row["messages"]); idx=min(row["turns"],len(scenario["turns"])-1)
    return jsonify(id=row["id"],scenario={k:v for k,v in scenario.items() if k!="turns"},mode=row["mode"],turns=row["turns"],completed=bool(row["completed"]),messages=messages,suggestions=scenario["turns"][idx]["suggestions"])

@app.post("/api/v1/conversations/<conversation_id>/turn")
def conversation_turn(conversation_id):
    payload=request.get_json(silent=True) or {}; learner=str(payload.get("text","" )).strip()[:500]
    if not learner: return jsonify(error="Enter or recognize a Japanese response first."),400
    with store.db() as c: row=c.execute("SELECT * FROM conversations WHERE id=?",(conversation_id,)).fetchone()
    if not row: return jsonify(error="Practice session not found."),404
    if row["completed"]: return jsonify(error="This practice session is finished."),409
    scenario=SCENARIO_MAP.get(row["scenario_id"]); messages=json.loads(row["messages"]); mode=row["mode"]
    if mode=="ai":
        profile=store.get_profile(); history=[{"role":"assistant" if m["speaker"]=="assistant" else "user","content":m["text"]} for m in messages if m["speaker"] in {"assistant","user"}]
        history.append({"role":"user","content":learner})
        try: result=generate_tutor_turn(profile["jlpt_level"],profile["learning_goal"],scenario,history)
        except ProviderUnavailable as exc: return jsonify(error=str(exc)),503
        tutor_text=result["reply_ja"] or result["follow_up"] or "もう一度言ってみましょう。"
        user_msg={"speaker":"user","text":learner,"created_at":store.stamp()}
        tutor_msg={"speaker":"assistant","text":tutor_text,"translation":result["reply_en"],"correction":result["correction_ja"],"explanation":result["explanation_en"],"new_words":result["new_words"],"created_at":store.stamp()}
        messages.extend([user_msg,tutor_msg]); turns=row["turns"]+1; idx=0
        suggestions=result.get("suggestions") or scenario["turns"][0]["suggestions"]
        with store.db() as c: c.execute("UPDATE conversations SET turns=?,updated_at=?,messages=? WHERE id=?",(turns,store.stamp(),json.dumps(messages,ensure_ascii=False),conversation_id))
        store.log_activity("conversation_turn",0,{"scenario_id":scenario["id"]})
        return jsonify(mode="ai",message=tutor_msg,suggestions=suggestions,turns=turns)
    idx=min(row["turns"],len(scenario["turns"])-1); current=scenario["turns"][idx]
    match=next((item for item in current["suggestions"] if learner.strip(" 。.!！?？")==item["ja"].strip(" 。.!！?？")),None)
    user_msg={"speaker":"user","text":learner,"created_at":store.stamp()}; messages.append(user_msg)
    if not match:
        feedback={"speaker":"assistant","text":"このガイド練習では自由入力の文法チェックはできません。例文を選ぶと会話を続けられます。","translation":"This guided exercise cannot check free-text grammar. Choose a suggested line to continue.","created_at":store.stamp()}; messages.append(feedback)
        with store.db() as c: c.execute("UPDATE conversations SET updated_at=?,messages=? WHERE id=?",(store.stamp(),json.dumps(messages,ensure_ascii=False),conversation_id))
        return jsonify(mode="guided",message=feedback,suggestions=current["suggestions"],turns=row["turns"],free_text_checked=False)
    next_index=min(idx+1,len(scenario["turns"])-1); next_turn=scenario["turns"][next_index]
    reply={"speaker":"assistant","text":next_turn["ja"],"translation":next_turn["en"],"created_at":store.stamp()}; messages.append(reply); turns=row["turns"]+1
    with store.db() as c: c.execute("UPDATE conversations SET turns=?,updated_at=?,messages=? WHERE id=?",(turns,store.stamp(),json.dumps(messages,ensure_ascii=False),conversation_id))
    store.log_activity("conversation_turn",0,{"scenario_id":scenario["id"]})
    return jsonify(mode="guided",message=reply,suggestions=next_turn["suggestions"],turns=turns,free_text_checked=False,accepted_suggestion=True)

@app.post("/api/v1/conversations/<conversation_id>/finish")
def conversation_finish(conversation_id):
    with store.db() as c: row=c.execute("SELECT * FROM conversations WHERE id=?",(conversation_id,)).fetchone()
    if not row: return jsonify(error="Practice session not found."),404
    if not row["completed"]:
        ctime=datetime.fromisoformat(row["created_at"]); elapsed=min(7200,max(0,int((datetime.now(timezone.utc)-ctime).total_seconds())))
        with store.db() as c: c.execute("UPDATE conversations SET completed=1,updated_at=? WHERE id=?",(store.stamp(),conversation_id))
        store.log_activity("conversation_completed",elapsed,{"scenario_id":row["scenario_id"],"turns":row["turns"],"mode":row["mode"]})
    scenario=SCENARIO_MAP[row["scenario_id"]]
    messages=json.loads(row["messages"]); corrections=[{"text":m.get("text",""),"correction":m.get("correction",""),"explanation":m.get("explanation","")} for m in messages if m.get("speaker")=="assistant" and m.get("correction")]
    learned=[]
    for msg in messages:
        for word in msg.get("new_words",[]):
            if word not in learned: learned.append(word)
    return jsonify(completed=True,scenario=scenario["title"],turns=row["turns"],mode=row["mode"],vocabulary=learned or scenario["vocabulary"],corrections=corrections,summary=f"You practiced {scenario['title'].lower()} and completed {row['turns']} learner turns.",next_practice="Review the expressions you want to remember, then try another scene.",feedback_note=("Scripted guided practice; no free-text grammar or pronunciation assessment was performed." if row["mode"]=="guided" else "Pronunciation was not scored. Review the tutor's text corrections and vocabulary."))

@app.get("/api/v1/conversations")
def conversation_history():
    with store.db() as c: rows=c.execute("SELECT id,scenario_id,mode,turns,completed,created_at,updated_at FROM conversations ORDER BY created_at DESC LIMIT 30").fetchall()
    return jsonify(items=[dict(r,title=SCENARIO_MAP.get(r["scenario_id"],{}).get("title","Practice")) for r in rows])

@app.delete("/api/v1/conversations/<conversation_id>")
def conversation_delete(conversation_id):
    with store.db() as c: cur=c.execute("DELETE FROM conversations WHERE id=?",(conversation_id,))
    if cur.rowcount==0: return jsonify(error="Practice session not found."),404
    return jsonify(ok=True)


def main():
    parser=argparse.ArgumentParser(description="Japanese Practice web and learning API.")
    parser.add_argument("--host",default="0.0.0.0"); parser.add_argument("--port",type=int,default=5055)
    parser.add_argument("--access-code",default=os.environ.get("SAKURA_ACCESS_CODE",""))
    args=parser.parse_args(); global ACCESS_CODE; ACCESS_CODE=args.access_code.strip()
    store.initialize()
    app.run(host=args.host,port=args.port,debug=False,threaded=True)

if __name__=="__main__": main()
