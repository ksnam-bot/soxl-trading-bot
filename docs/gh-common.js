// Shared GitHub Contents API helpers for the settings/positions editor pages.
// The PAT lives only in this browser's localStorage — never sent anywhere but api.github.com.
const LS_OWNER = 'soxl_gh_owner', LS_REPO = 'soxl_gh_repo', LS_TOKEN = 'soxl_gh_token', LS_BRANCH = 'soxl_gh_branch';

function ghCreds() {
  return {
    owner: localStorage.getItem(LS_OWNER) || '',
    repo: localStorage.getItem(LS_REPO) || '',
    token: localStorage.getItem(LS_TOKEN) || '',
    branch: localStorage.getItem(LS_BRANCH) || 'main',
  };
}
function hasGhCreds() {
  const c = ghCreds();
  return !!(c.owner && c.repo && c.token);
}
function saveGhCreds(owner, repo, token, branch) {
  localStorage.setItem(LS_OWNER, owner);
  localStorage.setItem(LS_REPO, repo);
  localStorage.setItem(LS_TOKEN, token);
  localStorage.setItem(LS_BRANCH, branch || 'main');
}
function clearGhCreds() {
  [LS_OWNER, LS_REPO, LS_TOKEN, LS_BRANCH].forEach(k => localStorage.removeItem(k));
}

function b64encodeUnicode(str) {
  const bytes = new TextEncoder().encode(str);
  let binary = '';
  bytes.forEach(b => binary += String.fromCharCode(b));
  return btoa(binary);
}
function b64decodeUnicode(b64) {
  const binary = atob(b64.replace(/\n/g, ''));
  const bytes = Uint8Array.from(binary, c => c.charCodeAt(0));
  return new TextDecoder('utf-8').decode(bytes);
}

async function ghGetFile(path) {
  const c = ghCreds();
  const res = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}/contents/${path}?ref=${c.branch}`, {
    headers: { Authorization: `Bearer ${c.token}`, Accept: 'application/vnd.github+json' },
  });
  if (!res.ok) throw new Error(`GitHub 읽기 실패 (${res.status}) ${path}`);
  const json = await res.json();
  return { sha: json.sha, data: JSON.parse(b64decodeUnicode(json.content)) };
}

async function ghPutFile(path, dataObj, sha, message) {
  const c = ghCreds();
  const content = b64encodeUnicode(JSON.stringify(dataObj, null, 2) + '\n');
  const res = await fetch(`https://api.github.com/repos/${c.owner}/${c.repo}/contents/${path}`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${c.token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ message, content, sha, branch: c.branch }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub 저장 실패 (${res.status}): ${body.slice(0, 200)}`);
  }
  return res.json();
}

async function testGhConnection(owner, repo, token) {
  const res = await fetch(`https://api.github.com/repos/${owner}/${repo}`, {
    headers: { Authorization: `Bearer ${token}`, Accept: 'application/vnd.github+json' },
  });
  if (!res.ok) throw new Error(`연결 실패 (${res.status}) — 저장소 이름이나 토큰을 확인해주세요`);
  return res.json();
}

function toast(msg, ms = 3500) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), ms);
}

function fmtPct(x, decimals = 2) {
  const v = Number(x) * 100;
  const d = Math.abs(v) < 0.01 && v !== 0 ? 5 : decimals;
  return v.toFixed(d).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '') + '%';
}
function money(x) { return '$' + Number(x).toLocaleString('en-US'); }
function money2(x) { return '$' + Number(x).toFixed(2); }

function renderGhSetupForm(introText) {
  return `<div class="card">
    <h2>GitHub 연결</h2>
    <div class="sub">${introText}</div>
    <div class="help">
      1. github.com 우측 상단 프로필 → <b>Settings</b> → 맨 아래 <b>Developer settings</b><br>
      2. <b>Personal access tokens → Fine-grained tokens → Generate new token</b><br>
      3. Repository access: <b>Only select repositories</b> → 이 저장소 선택<br>
      4. Permissions → <b>Contents: Read and write</b> 로 설정 → Generate token<br>
      5. 생성된 토큰(한 번만 보여줌)을 복사해서 아래에 입력
    </div>
    <form class="setup-form" id="setupForm">
      <input name="owner" placeholder="GitHub 계정명 (예: khbasket)" required />
      <input name="repo" placeholder="저장소 이름 (예: soxl-trading-bot)" required />
      <input name="token" type="password" placeholder="개인 액세스 토큰 (ghp_... 또는 github_pat_...)" required />
      <button type="submit">연결하기</button>
    </form>
  </div>`;
}

function wireGhSetupForm(onConnected) {
  document.getElementById('setupForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target;
    const owner = f.owner.value.trim(), repo = f.repo.value.trim(), token = f.token.value.trim();
    try {
      await testGhConnection(owner, repo, token);
      saveGhCreds(owner, repo, token, 'main');
      toast('연결 성공 ✅');
      onConnected();
    } catch (err) {
      toast(err.message, 5000);
    }
  });
}
