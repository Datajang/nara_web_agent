const API = '/api';
let token = localStorage.getItem('token');
let currentProjectId = null;
let currentConvId = null;
let currentStep = null;
let currentProjectProfile = null;
let allProjects = [];
let currentAbortController = null;

async function apiFetch(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  try {
    return await fetch(API + path, { ...opts, headers });
  } catch { return null; }
}

function showAuthError(msg) {
  const err = document.getElementById('auth-error');
  err.textContent = msg;
  err.classList.remove('hidden');
}

function showRegError(msg) {
  const err = document.getElementById('reg-error');
  err.textContent = msg;
  err.classList.remove('hidden');
}

document.getElementById('go-register-btn').addEventListener('click', () => {
  document.getElementById('login-panel').classList.add('hidden');
  document.getElementById('register-panel').classList.remove('hidden');
  document.getElementById('auth-error').classList.add('hidden');
  document.getElementById('reg-error').classList.add('hidden');
  document.getElementById('reg-email').value = '';
  document.getElementById('reg-password').value = '';
});

document.getElementById('go-login-btn').addEventListener('click', () => {
  document.getElementById('register-panel').classList.add('hidden');
  document.getElementById('login-panel').classList.remove('hidden');
});

function logout() {
  localStorage.removeItem('token');
  token = null;
  location.reload();
}

// ── AUTH ──────────────────────────────────────────────────────────────────────

document.getElementById('login-btn').addEventListener('click', async () => {
  const email = document.getElementById('email').value.trim();
  const password = document.getElementById('password').value;
  document.getElementById('auth-error').classList.add('hidden');

  if (!email || !password) {
    showAuthError('이메일과 비밀번호를 입력하세요');
    return;
  }

  const resp = await fetch(API + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  if (resp && resp.ok) {
    const data = await resp.json();
    token = data.access_token;
    localStorage.setItem('token', token);
    document.getElementById('user-email').textContent = email;
    showApp();
  } else {
    showAuthError('이메일 또는 비밀번호가 올바르지 않습니다');
  }
});

document.getElementById('register-btn').addEventListener('click', async () => {
  const email = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  document.getElementById('reg-error').classList.add('hidden');

  if (!email || !password) {
    showRegError('이메일과 비밀번호를 입력하세요');
    return;
  }

  const resp = await fetch(API + '/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password })
  });
  if (resp && resp.ok) {
    // 가입 성공 → 자동 로그인
    const loginResp = await fetch(API + '/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    if (loginResp && loginResp.ok) {
      const data = await loginResp.json();
      token = data.access_token;
      localStorage.setItem('token', token);
      document.getElementById('user-email').textContent = email;
      showApp();
    } else {
      document.getElementById('go-login-btn').click();
    }
  } else if (resp) {
    const data = await resp.json().catch(() => ({}));
    showRegError(data.detail === 'Email already registered' ? '이미 등록된 이메일입니다' : '회원가입 실패');
  } else {
    showRegError('서버 연결 실패');
  }
});

// ── STREAMING ─────────────────────────────────────────────────────────────────

function setStreaming(on) {
  document.getElementById('stop-btn').classList.toggle('hidden', !on);
  document.getElementById('send-btn').disabled = on;
  document.getElementById('msg-input').disabled = on;
}

document.getElementById('stop-btn').addEventListener('click', () => {
  if (currentAbortController) currentAbortController.abort();
});

document.getElementById('send-btn').addEventListener('click', sendMessage);
document.getElementById('msg-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

async function sendMessage() {
  if (!currentConvId) return;
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendUserBubble(text);

  currentAbortController = new AbortController();
  setStreaming(true);

  try {
    const resp = await fetch(API + `/conversations/${currentConvId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({ message: text }),
      signal: currentAbortController.signal
    });
    if (!resp || !resp.ok || !resp.body) { appendErrorBubble('서버 오류'); return; }
    await readStream(resp.body);
  } catch (e) {
    if (e.name !== 'AbortError') appendErrorBubble('서버 오류');
  } finally {
    setStreaming(false);
    currentAbortController = null;
  }
}

async function readStream(body) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let assistantBubble = null;
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const payload = JSON.parse(line.slice(6));
          if (payload.type === 'token') {
            if (!assistantBubble) assistantBubble = appendAssistantBubble('');
            assistantBubble.textContent += payload.content;
          } else if (payload.type === 'cards') {
            currentStep = 'search';
            renderCards(payload.content);
          } else if (payload.type === 'action' && payload.content === 'bookmark_prompt') {
            currentStep = 'chat';
            document.getElementById('new-search-bar').classList.remove('hidden');
            showBookmarkPrompt();
          } else if (payload.type === 'done') {
            if (currentStep !== 'search') {
              document.getElementById('new-search-bar').classList.remove('hidden');
            }
          } else if (payload.type === 'status') {
            if (!assistantBubble) assistantBubble = appendAssistantBubble(payload.content);
            else assistantBubble.textContent = payload.content;
          }
        } catch { /* ignore malformed lines */ }
      }
    }
  } finally {
    reader.cancel();
  }
}

// ── BID CARDS ─────────────────────────────────────────────────────────────────

function renderCards(cards) {
  if (cards.length === 0) {
    const el = document.createElement('div');
    el.className = 'bubble assistant';
    el.textContent = '검색 결과가 없습니다. 다른 키워드로 검색해보세요.';
    appendToChatDisplay(el);
    document.getElementById('new-search-bar').classList.remove('hidden');
    return;
  }
  const container = document.createElement('div');
  container.className = 'cards-container';
  cards.forEach(card => {
    const el = document.createElement('div');
    el.className = `bid-card ${card.is_open ? 'open' : 'closed'}`;
    const pageLink = card.bid_page_url
      ? `<a class="card-link" href="${card.bid_page_url}" target="_blank" rel="noopener">나라장터 보기</a>`
      : '';
    el.innerHTML = `
      <div class="card-title">${card.bid_title}</div>
      <div class="card-meta">마감: ${card.deadline || '-'} | 예산: ${card.budget || '-'}</div>
      <div class="card-actions">${pageLink}<button class="analyze-btn">분석하기</button></div>`;
    el.querySelector('.analyze-btn').addEventListener('click', () => analyzeCard(card));
    container.appendChild(el);
  });
  appendToChatDisplay(container);
}

async function analyzeCard(card) {
  appendUserBubble(`[분석 요청] ${card.bid_title}`);

  currentAbortController = new AbortController();
  setStreaming(true);

  try {
    const resp = await fetch(API + `/conversations/${currentConvId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
      body: JSON.stringify({
        message: `${card.bid_title} 분석`,
        selected_bid: { bid_title: card.bid_title, file_url: card.file_url, filename: card.filename || 'document.hwp', bid_page_url: card.bid_page_url || '' }
      }),
      signal: currentAbortController.signal
    });
    window._lastAnalysis = { bid_title: card.bid_title };
    if (!resp || !resp.ok || !resp.body) return;

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let bubble = null;
    let buf = '';
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n'); buf = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const p = JSON.parse(line.slice(6));
            if (p.type === 'token') {
              if (!bubble) bubble = appendAssistantBubble('');
              bubble.textContent += p.content;
              if (window._lastAnalysis) window._lastAnalysis.summary = bubble.textContent;
            } else if (p.type === 'action' && p.content === 'bookmark_prompt') {
              showBookmarkPrompt();
              document.getElementById('new-search-bar').classList.remove('hidden');
              currentStep = 'chat';
            }
          } catch {}
        }
      }
    } finally {
      reader.cancel();
    }
  } catch (e) {
    if (e.name !== 'AbortError') appendErrorBubble('분석 오류');
  } finally {
    setStreaming(false);
    currentAbortController = null;
  }
}

// ── BOOKMARK ──────────────────────────────────────────────────────────────────

document.getElementById('new-search-btn').addEventListener('click', () => {
  currentStep = null;
  document.getElementById('new-search-bar').classList.add('hidden');
});

function showBookmarkPrompt() {
  const el = document.createElement('div');
  el.className = 'bookmark-prompt';
  el.innerHTML = `<span>이 공고를 북마크에 저장하시겠습니까?</span>
    <button id="do-bookmark">저장</button><button id="skip-bookmark">건너뛰기</button>`;
  el.querySelector('#do-bookmark').addEventListener('click', async () => {
    const a = window._lastAnalysis || {};
    await apiFetch(`/projects/${currentProjectId}/bookmarks`, {
      method: 'POST',
      body: JSON.stringify({ bid_title: a.bid_title || '분석된 공고', analysis_summary: a.summary || '' })
    });
    el.remove();
    await loadBookmarks();
  });
  el.querySelector('#skip-bookmark').addEventListener('click', () => el.remove());
  appendToChatDisplay(el);
}

// ── PROFILE MODAL ─────────────────────────────────────────────────────────────

document.getElementById('edit-profile-btn').addEventListener('click', () => {
  if (!currentProjectId) return;
  document.getElementById('profile-textarea').value = currentProjectProfile || '';
  document.getElementById('profile-modal').classList.remove('hidden');
});

document.getElementById('profile-cancel-btn').addEventListener('click', () => {
  document.getElementById('profile-modal').classList.add('hidden');
});

document.getElementById('profile-save-btn').addEventListener('click', async () => {
  const profile = document.getElementById('profile-textarea').value.trim();
  const resp = await apiFetch(`/projects/${currentProjectId}`, {
    method: 'PUT',
    body: JSON.stringify({ department_profile: profile })
  });
  if (resp && resp.ok) {
    const p = await resp.json();
    currentProjectProfile = p.department_profile;
    const idx = allProjects.findIndex(x => x.id === currentProjectId);
    if (idx !== -1) allProjects[idx].department_profile = currentProjectProfile;
  }
  document.getElementById('profile-modal').classList.add('hidden');
});

// ── CHAT UI HELPERS ───────────────────────────────────────────────────────────

function appendToChatDisplay(el) {
  const c = document.getElementById('chat-messages');
  c.appendChild(el);
  c.scrollTop = c.scrollHeight;
}
function appendUserBubble(text) {
  const el = document.createElement('div');
  el.className = 'bubble user'; el.textContent = text; appendToChatDisplay(el);
}
function appendAssistantBubble(text) {
  const el = document.createElement('div');
  el.className = 'bubble assistant'; el.textContent = text; appendToChatDisplay(el); return el;
}
function appendErrorBubble(text) {
  const el = document.createElement('div');
  el.className = 'bubble error'; el.textContent = '오류: ' + text; appendToChatDisplay(el);
}

// ── APP INIT ──────────────────────────────────────────────────────────────────

async function showApp() {
  document.getElementById('auth-overlay').classList.add('hidden');
  document.getElementById('app').classList.remove('hidden');
  await loadProjects();
}

async function loadProjects() {
  const resp = await apiFetch('/projects');
  if (!resp || !resp.ok) return;
  allProjects = await resp.json();
  const sel = document.getElementById('project-select');
  sel.innerHTML = '';
  allProjects.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.id; opt.textContent = p.name; sel.appendChild(opt);
  });
  if (allProjects.length > 0) {
    currentProjectId = allProjects[0].id;
    currentProjectProfile = allProjects[0].department_profile;
    await loadConversations();
    await loadBookmarks();
  }
}

async function loadConversations() {
  const resp = await apiFetch(`/projects/${currentProjectId}/conversations`);
  if (!resp || !resp.ok) return;
  const convs = await resp.json();
  const list = document.getElementById('conv-list');
  list.innerHTML = '';
  convs.forEach(c => {
    const el = document.createElement('div');
    el.className = 'conv-item'; el.textContent = c.title || `대화 #${c.id}`;
    el.addEventListener('click', () => selectConversation(c.id)); list.appendChild(el);
  });
  if (convs.length > 0) await selectConversation(convs[convs.length - 1].id);
}

async function loadBookmarks() {
  const resp = await apiFetch(`/projects/${currentProjectId}/bookmarks`);
  if (!resp || !resp.ok) return;
  const bms = await resp.json();
  const list = document.getElementById('bookmark-list');
  list.innerHTML = '<strong>🔖 북마크</strong>';
  bms.forEach(b => {
    const el = document.createElement('div'); el.className = 'bookmark-item'; el.textContent = b.bid_title; list.appendChild(el);
  });
}

async function selectConversation(convId) {
  currentConvId = convId; currentStep = null;
  document.getElementById('chat-messages').innerHTML = '';
  document.getElementById('new-search-bar').classList.add('hidden');
  const resp = await apiFetch(`/conversations/${convId}/messages`);
  if (!resp || !resp.ok) return;
  const messages = await resp.json();
  messages.forEach(m => {
    if (m.role === 'user') appendUserBubble(m.content);
    else {
      if (m.step === 'search') {
        try { renderCards(JSON.parse(m.metadata_ || '{}').cards || []); } catch { appendAssistantBubble(m.content); }
      } else appendAssistantBubble(m.content);
      if (m.step === 'analyze' || m.step === 'chat') document.getElementById('new-search-bar').classList.remove('hidden');
      currentStep = m.step;
    }
  });
}

document.getElementById('new-conv-btn').addEventListener('click', async () => {
  const resp = await apiFetch(`/projects/${currentProjectId}/conversations`, { method: 'POST', body: JSON.stringify({ title: null }) });
  if (resp && resp.ok) await loadConversations();
});

document.getElementById('new-project-btn').addEventListener('click', async () => {
  const name = prompt('새 프로젝트 이름:');
  if (!name) return;
  await apiFetch('/projects', { method: 'POST', body: JSON.stringify({ name }) });
  await loadProjects();
});

document.getElementById('project-select').addEventListener('change', async e => {
  currentProjectId = parseInt(e.target.value);
  const project = allProjects.find(p => p.id === currentProjectId);
  currentProjectProfile = project ? project.department_profile : null;
  await loadConversations();
  await loadBookmarks();
});

document.getElementById('logout-btn').addEventListener('click', logout);

if (token) showApp();
else document.getElementById('auth-overlay').classList.remove('hidden');
