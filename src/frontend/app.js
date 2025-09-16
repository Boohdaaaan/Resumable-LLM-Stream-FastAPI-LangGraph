const API_BASE = ""; // same origin

// State
let currentThreadId = null;
let source = null; // EventSource

const els = {
  threads: document.getElementById("threads"),
  threadItemTpl: document.getElementById("thread-item-template"),
  messages: document.getElementById("messages"),
  messageTpl: document.getElementById("message-template"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  composer: document.getElementById("composer"),
  newChat: document.getElementById("new-chat"),
  chatTitle: document.getElementById("chat-title"),
};

function setSendDisabled(disabled) {
  els.send.disabled = !!disabled;
  els.send.setAttribute("aria-disabled", disabled ? "true" : "false");
}

function fmtDate(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return ""; }
}

function threadTimestamp(thread) {
  return thread.last_activity_time || new Date().toISOString();
}

function createThreadElement(thread) {
  const node = els.threadItemTpl.content.firstElementChild.cloneNode(true);
  node.dataset.id = thread.id;
  const titleEl = node.querySelector(".title");
  const metaEl = node.querySelector(".meta");
  const renameBtn = node.querySelector(".rename");
  const deleteBtn = node.querySelector(".delete");

  titleEl.textContent = thread.chat_name || "New Chat";
  metaEl.textContent = fmtDate(threadTimestamp(thread));

  node.addEventListener("click", () => selectThread(thread.id, titleEl.textContent));

  renameBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    const currentName = titleEl.textContent || "New Chat";
    const name = prompt("Rename chat to:", currentName);
    if (name && name.trim()) {
      const trimmed = name.trim();
      titleEl.textContent = trimmed;
      if (currentThreadId === thread.id) {
        els.chatTitle.textContent = trimmed;
      }
      try {
        await renameThread(thread.id, trimmed);
        await fetchThreads();
      } catch {}
    }
  });

  deleteBtn.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!confirm("Delete this chat?")) return;
    try {
      await deleteThread(thread.id);
    } catch {}
    // Optimistically remove from UI
    node.remove();
    if (currentThreadId === thread.id) {
      clearMessages();
      currentThreadId = null;
      els.chatTitle.textContent = "New Chat";
      const list = await fetchThreads().catch(() => []);
      if (list && list.length) {
        selectThread(list[0].id, list[0].chat_name).catch(() => {});
      }
    } else {
      fetchThreads().catch(() => {});
    }
  });

  return node;
}

function setActiveThreadInSidebar() {
  for (const btn of els.threads.querySelectorAll(".thread")) {
    btn.classList.toggle("active", btn.dataset.id === currentThreadId);
  }
}

function appendMessage({ type, content }) {
  const node = els.messageTpl.content.firstElementChild.cloneNode(true);
  node.classList.add(type === "human" || type === "user" ? "user" : "ai");
  node.querySelector(".bubble").textContent = content || "";
  els.messages.appendChild(node);
  els.messages.scrollTop = els.messages.scrollHeight;
  return node.querySelector(".bubble");
}

function clearMessages() {
  els.messages.innerHTML = "";
}

async function fetchThreads() {
  const res = await fetch(`${API_BASE}/threads`);
  if (!res.ok) throw new Error("Failed to fetch threads");
  const data = await res.json();
  // Sort by last activity time desc
  data.sort((a, b) => {
    const ta = Date.parse(threadTimestamp(a)) || 0;
    const tb = Date.parse(threadTimestamp(b)) || 0;
    return tb - ta;
  });
  els.threads.innerHTML = "";
  data.forEach((t) => els.threads.appendChild(createThreadElement(t)));
  setActiveThreadInSidebar();
  return data;
}

async function fetchThreadMessages(threadId) {
  const res = await fetch(`${API_BASE}/thread?thread_id=${encodeURIComponent(threadId)}`);
  if (!res.ok) throw new Error("Failed to fetch thread messages");
  return res.json();
}

async function deleteThread(threadId) {
  const res = await fetch(`${API_BASE}/thread?thread_id=${encodeURIComponent(threadId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete thread");
}

async function renameThread(threadId, chatName) {
  const res = await fetch(`${API_BASE}/thread?thread_id=${encodeURIComponent(threadId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_name: chatName }),
  });
  if (!res.ok) throw new Error("Failed to rename thread");
}

async function sendMessage(threadId, message) {
  const res = await fetch(`${API_BASE}/chat/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, message }),
  });
  if (!res.ok) throw new Error("Failed to send message");
}

function openStream(threadId, onChunk, onEnd, onToolCall) {
  closeStream();
  const url = `${API_BASE}/chat/stream?thread_id=${encodeURIComponent(threadId)}`;
  const es = new EventSource(url);
  setSendDisabled(true);
  // Default "message" events are token chunks now (plain text)
  es.onmessage = (ev) => {
    if (typeof ev.data === "string" && ev.data.length) {
      onChunk(ev.data);
    }
  };
  // Explicit chunk events (if server emits custom 'chunk')
  es.addEventListener("chunk", (ev) => {
    if (typeof ev.data === "string" && ev.data.length) {
      onChunk(ev.data);
    }
  });
  // Server emits custom system events for lifecycle notifications
  es.addEventListener("system", (ev) => {
    if ((ev.data || "").trim() === "end") {
      onEnd?.();
      closeStream();
      setSendDisabled(false);
    }
  });
  // Tool call notifications
  es.addEventListener("tool_call", (ev) => {
    if (typeof onToolCall === "function") {
      onToolCall(ev.data || "");
    }
  });
  // es.onerror = () => {
  //   // Close to prevent browser auto-reconnect spam when stream is empty/completed
  //   closeStream();
  // };
  source = es;
}

function closeStream() {
  if (source) {
    source.close();
    source = null;
  }
  // Re-enable send if it was disabled due to a previous stream
  setSendDisabled(false);
}

async function selectThread(threadId, chatName) {
  currentThreadId = threadId;
  els.chatTitle.textContent = chatName || "New Chat";
  setActiveThreadInSidebar();
  clearMessages();

  // Load messages, then start streaming
  const messages = await fetchThreadMessages(threadId);
  messages.forEach((m) => appendMessage(m));

  // Always open stream to receive any potential updates/tokens for this thread
  let aiBubble = null;
  let toolLoader = null;
  let toolLoaderTextEl = null;
  openStream(
    threadId,
    (chunk) => {
      if (!aiBubble) {
        aiBubble = appendMessage({ type: "ai", content: "" });
      }
      aiBubble.textContent += chunk;
      els.messages.scrollTop = els.messages.scrollHeight;
      // any chunk should clear tool loader
      if (toolLoader && toolLoader.parentElement) {
        toolLoader.remove();
        toolLoader = null;
        toolLoaderTextEl = null;
      }
    },
    () => {
      aiBubble = null;
      if (toolLoader && toolLoader.parentElement) {
        toolLoader.remove();
        toolLoader = null;
        toolLoaderTextEl = null;
      }
      // refresh threads to update sort/title if backend updates metadata on finish
      fetchThreads().catch(() => {});
    },
    (text) => {
      if (!aiBubble) {
        aiBubble = appendMessage({ type: "ai", content: "" });
      }
      const messageEl = aiBubble.parentElement;
      if (!messageEl) return;
      if (!toolLoader) {
        toolLoader = document.createElement("div");
        toolLoader.className = "tool-call";
        const spinner = document.createElement("span");
        spinner.className = "spinner";
        toolLoaderTextEl = document.createElement("span");
        toolLoaderTextEl.className = "text";
        toolLoader.appendChild(spinner);
        toolLoader.appendChild(toolLoaderTextEl);
        messageEl.appendChild(toolLoader);
      }
      if (!toolLoaderTextEl) {
        toolLoaderTextEl = document.createElement("span");
        toolLoaderTextEl.className = "text";
        toolLoader.appendChild(toolLoaderTextEl);
      }
      toolLoaderTextEl.textContent = String(text || "").trim();
    }
  );
}

function autoGrowTextarea() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 160) + "px";
}

function getActiveThreadFromSidebar() {
  const active = els.threads.querySelector(".thread.active");
  return active?.dataset.id || null;
}


// Event handlers
els.composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  const value = els.input.value.trim();
  if (!value) return;

  // If we are in draft new chat mode (no currentThreadId), create an id now on first send
  if (!currentThreadId) {
    const newId = (typeof crypto !== "undefined" && crypto.randomUUID)
      ? crypto.randomUUID()
      : ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c => (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16));
    currentThreadId = newId;
    els.chatTitle.textContent = "New Chat";
  }

  // Show user's message immediately
  appendMessage({ type: "human", content: value });
  els.input.value = "";
  autoGrowTextarea();

  // Send message and open stream
  await sendMessage(currentThreadId, value);

  let aiBubble = null;
  let toolLoader = null;
  let toolLoaderTextEl = null;
  openStream(
    currentThreadId,
    (chunk) => {
      if (!aiBubble) aiBubble = appendMessage({ type: "ai", content: "" });
      aiBubble.textContent += chunk;
      if (toolLoader && toolLoader.parentElement) {
        toolLoader.remove();
        toolLoader = null;
        toolLoaderTextEl = null;
      }
    },
    () => {
      aiBubble = null;
      if (toolLoader && toolLoader.parentElement) {
        toolLoader.remove();
        toolLoader = null;
        toolLoaderTextEl = null;
      }
      // After full response, refresh threads to get generated title for the new chat
      fetchThreads().catch(() => {});
    },
    (text) => {
      if (!aiBubble) aiBubble = appendMessage({ type: "ai", content: "" });
      const messageEl = aiBubble.parentElement;
      if (!messageEl) return;
      if (!toolLoader) {
        toolLoader = document.createElement("div");
        toolLoader.className = "tool-call";
        const spinner = document.createElement("span");
        spinner.className = "spinner";
        toolLoaderTextEl = document.createElement("span");
        toolLoaderTextEl.className = "text";
        toolLoader.appendChild(spinner);
        toolLoader.appendChild(toolLoaderTextEl);
        messageEl.appendChild(toolLoader);
      }
      if (!toolLoaderTextEl) {
        toolLoaderTextEl = document.createElement("span");
        toolLoaderTextEl.className = "text";
        toolLoader.appendChild(toolLoaderTextEl);
      }
      toolLoaderTextEl.textContent = String(text || "").trim();
    }
  );
});

els.input.addEventListener("input", autoGrowTextarea);

els.newChat.addEventListener("click", () => {
  // Do not create sidebar item yet; show an empty draft chat
  currentThreadId = null;
  els.chatTitle.textContent = "New Chat";
  clearMessages();
  setActiveThreadInSidebar();
});

// Initial load: get threads; if any, select first. Also if a thread is selected, load messages then open stream.
(async function init() {
  try {
    const list = await fetchThreads();
    if (list.length) {
      await selectThread(list[0].id, list[0].chat_name);
    }
  } catch (e) {
    console.error(e);
  }
})();
