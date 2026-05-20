from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
from groq import Groq
import requests
import os
import uuid
import threading
import webbrowser
import time

app = Flask(__name__)
app.secret_key = "pulseai-royal-secret-2024"

# ── UPDATE YOUR_PASSWORD BELOW ──────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "mysql+pymysql://root:Satya%402006@localhost/pulseai_db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ── PASTE YOUR API KEYS HERE ─────────────────────────────
GROQ_API_KEY = "your-groq-api-key-here"
SERP_API_KEY = "your-serp-api-key-here"
groq_client = Groq(api_key=GROQ_API_KEY)
# ─── MODELS ──────────────────────────────────────────────
class User(db.Model):
    __tablename__ = "users"
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name       = db.Column(db.String(100), nullable=False)
    email      = db.Column(db.String(150), unique=True, nullable=False)
    password   = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sessions   = db.relationship("ChatSession", backref="user", lazy=True,
                                 cascade="all, delete-orphan")

class ChatSession(db.Model):
    __tablename__ = "chat_sessions"
    id         = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title      = db.Column(db.String(200), nullable=False, default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages   = db.relationship("Message", backref="chat_session", lazy=True,
                                 cascade="all, delete-orphan")

class Message(db.Model):
    __tablename__ = "messages"
    id         = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String(36), db.ForeignKey("chat_sessions.id"), nullable=False)
    role       = db.Column(db.Enum("user", "model"), nullable=False)
    content    = db.Column(db.Text, nullable=False)
    has_search = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ─── AUTH DECORATOR ───────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ─── AUTH ROUTES ──────────────────────────────────────────
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("chat"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    data     = request.json
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid email or password"}), 401
    session["user_id"]    = user.id
    session["user_name"]  = user.name
    session["user_email"] = user.email
    return jsonify({"success": True, "name": user.name})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")
    data     = request.json
    name     = data.get("name", "").strip()
    email    = data.get("email", "").strip().lower()
    password = data.get("password", "")
    if not name or not email or not password:
        return jsonify({"error": "All fields are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered"}), 409
    user = User(name=name, email=email, password=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    session["user_id"]    = user.id
    session["user_name"]  = user.name
    session["user_email"] = user.email
    return jsonify({"success": True, "name": user.name})

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── CHAT PAGE ────────────────────────────────────────────
@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html",
                           user_name=session.get("user_name"),
                           user_email=session.get("user_email"))

# ─── API ROUTES ───────────────────────────────────────────
@app.route("/api/session/new", methods=["POST"])
@login_required
def new_session():
    s = ChatSession(user_id=session["user_id"])
    db.session.add(s)
    db.session.commit()
    return jsonify({"session_id": s.id, "title": s.title})

@app.route("/api/sessions", methods=["GET"])
@login_required
def get_sessions():
    sessions_list = ChatSession.query\
        .filter_by(user_id=session["user_id"])\
        .order_by(ChatSession.created_at.desc()).limit(30).all()
    return jsonify([{
        "id": s.id,
        "title": s.title,
        "created_at": s.created_at.strftime("%d %b, %I:%M %p")
    } for s in sessions_list])

@app.route("/api/session/<session_id>/messages", methods=["GET"])
@login_required
def get_messages(session_id):
    cs = ChatSession.query.filter_by(id=session_id, user_id=session["user_id"]).first()
    if not cs:
        return jsonify([])
    msgs = Message.query.filter_by(session_id=session_id).order_by(Message.created_at).all()
    return jsonify([{
        "role": m.role,
        "content": m.content,
        "has_search": m.has_search,
        "created_at": m.created_at.strftime("%I:%M %p")
    } for m in msgs])

@app.route("/api/chat", methods=["POST"])
@login_required
def chat_api():
    data       = request.json
    session_id = data.get("session_id")
    user_msg   = data.get("message", "").strip()
    if not user_msg or not session_id:
        return jsonify({"error": "Missing fields"}), 400
    cs = ChatSession.query.filter_by(id=session_id, user_id=session["user_id"]).first()
    if not cs:
        return jsonify({"error": "Session not found"}), 404
    if cs.title == "New Chat":
        cs.title = user_msg[:60] + ("..." if len(user_msg) > 60 else "")
        db.session.commit()
    db.session.add(Message(session_id=session_id, role="user", content=user_msg))
    db.session.commit()

    # ── SerpAPI Search ────────────────────────────────────
    search_keywords = ["latest","news","today","current","recent","2024","2025",
                       "price","weather","score","who is","who won","what happened",
                       "search","find","trending","live","now"]
    should_search    = any(kw in user_msg.lower() for kw in search_keywords)
    search_context   = ""
    search_performed = False
    if should_search and SERP_API_KEY:
        try:
            resp    = requests.get("https://serpapi.com/search", params={
                "q": user_msg, "api_key": SERP_API_KEY, "num": 5
            }, timeout=8)
            results = resp.json().get("organic_results", [])
            if results:
                search_context = "\n\n[Live Google Search Results]\n"
                for i, r in enumerate(results[:4], 1):
                    search_context += (
                        f"{i}. {r.get('title','')}\n"
                        f"   {r.get('snippet','')}\n"
                        f"   Link: {r.get('link','')}\n\n"
                    )
                search_performed = True
        except Exception:
            pass

    # ── Gemini API ────────────────────────────────────────
    past    = Message.query.filter_by(session_id=session_id)\
                           .order_by(Message.created_at).all()[:-1]
    history = [{"role": m.role, "parts": [m.content]} for m in past]

    system_instruction = (
    "You are PulseAI, a smart and friendly AI assistant. "
    "When Google search results are provided, use them to give accurate "
    "up-to-date answers and naturally mention sources. "
    "Keep answers short and to the point. "
    "For weather queries, just give the temperature and conditions in 1-2 lines. "
    "For simple questions, give simple short answers. "
    "Only give long answers when the topic truly requires it. "
    "Format responses clearly using markdown. Be helpful and conversational."
)
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_msg + search_context}
            ]
        )
        ai_reply = response.choices[0].message.content
    except Exception as e:
        ai_reply = f"API error: {str(e)}"

    db.session.add(Message(session_id=session_id, role="model",
                           content=ai_reply, has_search=search_performed))
    db.session.commit()
    return jsonify({"reply": ai_reply, "has_search": search_performed,
                    "session_title": cs.title})

@app.route("/api/session/<session_id>/delete", methods=["DELETE"])
@login_required
def delete_session(session_id):
    cs = ChatSession.query.filter_by(id=session_id, user_id=session["user_id"]).first()
    if cs:
        db.session.delete(cs)
        db.session.commit()
    return jsonify({"status": "deleted"})
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        print("PulseAI DB tables ready!")

    def open_browser():
        time.sleep(1)
        webbrowser.open("http://localhost:5000")

    threading.Thread(target=open_browser).start()
    app.run(debug=False, port=5000)