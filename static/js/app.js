// ── Markdown parser (CDN) ─────────────────────────────────
const ms = document.createElement("script");
ms.src   = "https://cdn.jsdelivr.net/npm/marked/marked.min.js";
document.head.appendChild(ms);
// ── State ─────────────────────────────────────────────────
let currentSessionId = null;
// ── DOM refs ──────────────────────────────────────────────
const messagesEl  = document.getElementById("messages");
const welcomeEl   = document.getElementById("welcome");
const userInput   = document.getElementById("userInput");
const sendBtn     = document.getElementById("sendBtn");
const sessionsEl  = document.getElementById("sessionsList");
const chatTitle   = document.getElementById("chatTitle");
const searchPill  = document.getElementById("searchPill");
// ── On load ───────────────────────────────────────────────
window.addEventListener("load", () => {
  loadSessions();
  startNewChat();
});
// ── Sidebar toggle ─────────────────────────────────────────
document.getElementById("toggleSb").addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("open");
});
// ── New Chat ───────────────────────────────────────────────
document.getElementById("newChatBtn").addEventListener("click", startNewChat);
async function startNewChat() {
  const res  = await fetch("/api/session/new", { method: "POST" });
  const data = await res.json();
  currentSessionId = data.session_id;
  messagesEl.innerHTML     = "";
  welcomeEl.style.display  = "flex";
  messagesEl.style.display = "none";
  chatTitle.textContent    = "New Conversation";
  searchPill.style.display = "none";
  loadSessions();
  userInput.focus();
}
// ── Load sessions in sidebar ───────────────────────────────
async function loadSessions() {
  const res  = await fetch("/api/sessions");
  const data = await res.json();
  sessionsEl.innerHTML = "";
  if (!data.length) {
    sessionsEl.innerHTML = '<div class="loading-sess">No chats yet</div>';
    return;
  }
  data.forEach(s => {
    const el = document.createElement("div");
    el.className = "sess-item" + (s.id === currentSessionId ? " active" : "");
    el.innerHTML = `
      <span class="sess-title">${esc(s.title)}</span>
      <span class="sess-time">${s.created_at}</span>
      <button class="del-btn" onclick="delSession('${s.id}', event)">✕</button>
    `;
    el.addEventListener("click", () => loadSession(s.id, s.title));
    sessionsEl.appendChild(el);
  });
}
// ── Load existing session ──────────────────────────────────
async function loadSession(id, title) {
  currentSessionId      = id;
  chatTitle.textContent = title;
  const res  = await fetch(`/api/session/${id}/messages`);
  const msgs = await res.json();
  welcomeEl.style.display  = "none";
  messagesEl.style.display = "flex";
  messagesEl.innerHTML     = "";
  msgs.forEach(m => addBubble(m.role, m.content, m.has_search, false));
  scrollBottom();
  loadSessions();
}
// ── Delete session ─────────────────────────────────────────
async function delSession(id, e) {
  e.stopPropagation();
  await fetch(`/api/session/${id}/delete`, { method: "DELETE" });
  if (id === currentSessionId) startNewChat();
  else loadSessions();
}
// ── Send message ───────────────────────────────────────────
sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
// Auto-resize textarea
userInput.addEventListener("input", () => {
  userInput.style.height = "auto";
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + "px";
});
async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || !currentSessionId) return;
  userInput.value        = "";
  userInput.style.height = "auto";
  sendBtn.disabled       = true;
  // Show messages area, hide welcome
  welcomeEl.style.display  = "none";
  messagesEl.style.display = "flex";
  // Show user bubble
  addBubble("user", text, false, true);
  // Show typing indicator
  const typId = showTyping();
  try {
    const res  = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId, message: text })
    });
    const data = await res.json();
    removeTyping(typId);
    if (data.error) {
      addBubble("model", "⚠️ " + data.error, false, true);
    } else {
      addBubble("model", data.reply, data.has_search, true);
      chatTitle.textContent = data.session_title;
      // Show web search pill for 4 seconds
      if (data.has_search) {
        searchPill.style.display = "flex";
        setTimeout(() => searchPill.style.display = "none", 4000);
      }
    }
  } catch {
    removeTyping(typId);
    addBubble("model", "⚠️ Network error. Please try again.", false, true);
  }

  sendBtn.disabled = false;
  loadSessions();
  scrollBottom();
}

// ── Suggestion chips ───────────────────────────────────────
function suggest(text) {
  userInput.value = text;
  sendMessage();
}

// ── Render message bubble ──────────────────────────────────
function addBubble(role, content, hasSearch, animate) {
  const isUser = role === "user";
  const row    = document.createElement("div");
  row.className = "msg-row " + (isUser ? "user" : "ai");
  if (!animate) row.style.animation = "none";

  const now  = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const html = typeof marked !== "undefined"
    ? marked.parse(content)
    : content.replace(/\n/g, "<br>");

  row.innerHTML = `
    <div class="avatar ${isUser ? "av-user" : "av-ai"}">${isUser ? "You" : "AI"}</div>
    <div class="bubble ${isUser ? "user" : "ai"}">
      <div class="bubble-meta">
        ${isUser ? "You" : "PulseAI"} &middot; ${now}
        ${hasSearch ? '<span class="stag">🔍 Web Search</span>' : ""}
      </div>
      <div>${html}</div>
    </div>`;

  messagesEl.appendChild(row);
  scrollBottom();
}

// ── Typing indicator ───────────────────────────────────────
function showTyping() {
  const id  = "typ-" + Date.now();
  const row = document.createElement("div");
  row.id    = id;
  row.className = "msg-row ai";
  row.innerHTML = `
    <div class="avatar av-ai">AI</div>
    <div class="bubble ai">
      <div class="typing">
        <span></span><span></span><span></span>
      </div>
    </div>`;
  messagesEl.appendChild(row);
  scrollBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}
function scrollBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function esc(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
// ── Helpers ───────────────────