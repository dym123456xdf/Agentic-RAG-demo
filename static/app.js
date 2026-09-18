/* 共享脚本 —— 会话/历史 API 封装 + 消息渲染(首页与管理页共用,避免两份拷贝漂移) */

// ---------- 工具 ----------
function escapeHtml(s) {
  return String(s).replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function showToast(msg, isErr) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast show" + (isErr ? " err" : "");
  setTimeout(() => t.className = "toast", 2200);
}

// ---------- 会话 API ----------
const SessionsAPI = {
  async list() {
    const r = await fetch("/sessions");
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "拉取会话失败");
    return d.sessions || [];
  },
  async create(title) {
    const r = await fetch("/sessions", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(title ? { title } : {}),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "创建会话失败");
    return d;
  },
  async remove(id) {
    const r = await fetch(`/sessions/${id}`, { method: "DELETE" });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "删除失败");
  },
  async messages(id) {
    const r = await fetch(`/sessions/${id}/messages`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "拉取历史失败");
    return d.messages || [];
  },
  async clear(id) {
    const r = await fetch(`/sessions/${id}/clear`, { method: "POST" });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "清空失败");
  },
};

// ---------- 消息渲染 ----------
// 把已 escape 的文本里 `![alt](/converted/...)` 渲染成 <img>。
// 仅放行 /converted/ 前缀:相对路径 / 外链 / LLM 编造的路径一律按原文显示、不发起加载
// (防注入与裂图)。alt/src 里的引号补转 &quot;(escapeHtml 不覆盖引号,防属性逃逸)。
function renderChatImages(escaped) {
  return escaped.replace(
    /!\[([^\]]*)\]\((\/converted\/[^\s"')]+)\)/g,
    (_, alt, src) =>
      `<img class="chat-img" src="${src.replace(/"/g, "&quot;")}" alt="${alt.replace(/"/g, "&quot;")}">`
  );
}

// 实时聊天:直接渲染来源与 meta;历史回溯(collapsed=true):来源与 meta 放进可展开的 <details>
function messageHtml(m, collapsed = false) {
  const cls = m.role === "user" ? "user" : "bot";
  // 图片只渲染在助手回答里;用户消息保持原文(自己输入的语法原文更直观)
  let inner = m.role === "user" ? escapeHtml(m.content) : renderChatImages(escapeHtml(m.content));

  if (m.role !== "user" && m.sources && m.sources.length) {
    let src = "<b>📎 参考来源</b>";
    for (const s of m.sources) {
      src += `<div class="src">[#${s.index}] <b>${escapeHtml(s.source)}</b> ` +
             `<span style="float:right;color:#888">score=${s.score}</span><br>` +
             `<span style="color:#555">${escapeHtml(String(s.content).slice(0, 200))}…</span></div>`;
    }
    if (collapsed) {
      inner += `<details><summary>展开来源与详情</summary><div class="sources">${src}</div>${metaHtml(m.meta)}</details>`;
    } else {
      inner += `<div class="sources">${src}</div>` + metaHtml(m.meta);
    }
  }
  return `<div class="msg ${cls}">${inner}</div>`;
}

function metaHtml(meta) {
  if (!meta) return "";
  return `<div class="meta">意图=${escapeHtml(meta.intent || "")} | ` +
         `召回=${meta.raw_count ?? "?"} → 重排后=${meta.after_count ?? "?"} | ` +
         `改写: ${escapeHtml(meta.rewritten || "")}</div>`;
}
