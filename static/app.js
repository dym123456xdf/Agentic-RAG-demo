/* 共享脚本 —— 会话/历史 API 封装 + 消息渲染(首页与管理页共用,避免两份拷贝漂移) */

// ---------- 内联 SVG 图标(stroke 跟随文字色,替代 emoji) ----------
const SVG = {
  // 文件(列表行)
  file: '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/></svg>',
  // 回形针(参考来源)
  clip: '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>',
  // 问号(历史问答的提问)
  help: '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><path d="M12 17h.01"/></svg>',
  // 警告(请求失败)
  alert: '<svg class="ic chat-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>',
  // 垃圾桶(删除按钮)
  trash: '<svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>',
};

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
    let src = `<b class="src-title">${SVG.clip}参考来源</b>`;
    for (const s of m.sources) {
      src += `<div class="src">[#${s.index}] <b>${escapeHtml(s.source)}</b> ` +
             `<span class="src-score">score=${s.score}</span><br>` +
             `<span class="src-snippet">${escapeHtml(String(s.content).slice(0, 200))}…</span></div>`;
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
