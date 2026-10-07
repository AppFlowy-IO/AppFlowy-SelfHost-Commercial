import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(scriptDir, '../..');
// The test has its own locked dependency; an existing Web checkout is optional.
const dependencyRoot = path.resolve(process.env.APPFLOWY_WEB_DIR || path.join(repo, 'ci'));
const require = createRequire(path.join(dependencyRoot, 'package.json'));
const { chromium, expect } = require('@playwright/test');
const root = path.resolve(process.env.SWARM_TEST_DIR || path.join(repo, 'docker-swarm/.local'));
const metadata = JSON.parse(fs.readFileSync(path.join(root, 'metadata.json'), 'utf8'));
const base = metadata.base_url;
if (!['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) throw new Error('UI smoke test requires a local test endpoint');
// A prior run must never signal readiness/completion for this new pair of clients.
for (const file of ['ui-replacement-ready.json', 'ui-replacement-complete']) fs.rmSync(path.join(root, file), { force: true });
const user = JSON.parse(fs.readFileSync(path.join(root, 'ordinary-user.json'), 'utf8'));
const apiState = JSON.parse(fs.readFileSync(path.join(root, 'api-state.json'), 'utf8'));
const marker = `SwarmUI${crypto.randomBytes(4).toString('hex')}`;
const result = { marker, started_at: new Date().toISOString(), checks: [], browsers: [] };
const save = (name, value) => fs.writeFileSync(path.join(root, name), JSON.stringify(value, null, 2), { mode: 0o600 });
async function token() {
  const r = await fetch(`${base}/gotrue/token?grant_type=password`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(user),
  });
  if (!r.ok) throw new Error(`Local GoTrue login HTTP ${r.status}`);
  const value = await r.json();
  value.expires_at ||= Math.floor(Date.now() / 1000) + value.expires_in;
  return value;
}
const tokens = [await token(), await token()];
const documentId = crypto.randomUUID();
const create = await fetch(`${base}/api/workspace/${apiState.workspace_id}/page-view`, {
  method: 'POST',
  headers: { 'content-type': 'application/json', authorization: `Bearer ${tokens[0].access_token}` },
  body: JSON.stringify({ parent_view_id: apiState.parent_id, layout: 0, name: marker,
    view_id: documentId, collab_id: documentId }),
});
const created = await create.json();
if (!create.ok || created.code !== 0) throw new Error(`Local UI doc creation failed HTTP${create.status} code${created.code}`);
const viewId = created.data.view_id;
result.workspace_id = apiState.workspace_id;
result.view_id = viewId;
result.url = `${base}/app/${apiState.workspace_id}/${viewId}`;
save('ui-target.json', { workspace_id: apiState.workspace_id, view_id: viewId, marker });
const channel = process.env.SWARM_BROWSER_CHANNEL || 'chromium';
const browser = await chromium.launch({ channel, headless: true });
const pages = [];
try {
  for (let i = 0; i < 2; i++) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript(({ tokenData, origin }) => {
      if (location.origin !== origin) return;
      if (!localStorage.getItem('token')) {
        localStorage.setItem('token', JSON.stringify(tokenData));
        localStorage.setItem('af_auth_token', tokenData.access_token);
        localStorage.setItem('af_refresh_token', tokenData.refresh_token);
        localStorage.setItem('af_user_id', tokenData.user.id);
      }
      const Native = window.WebSocket;
      window.__swarmWs = [];
      window.WebSocket = class extends Native {
        constructor(...args) {
          super(...args);
          const parsed = new URL(String(args[0]));
          const row = { url: `${parsed.protocol}//${parsed.host}${parsed.pathname}`, open: 0, close: 0, errors: 0, received: 0 };
          window.__swarmWs.push({ socket: this, row });
          this.addEventListener('open', () => row.open++);
          this.addEventListener('close', () => row.close++);
          this.addEventListener('error', () => row.errors++);
          this.addEventListener('message', () => row.received++);
        }
      };
    }, { tokenData: tokens[i], origin: base });
    const page = await context.newPage();
    const metrics = { index: i, websocket_connections: 0, frames_sent: 0, frames_received: 0, websocket_errors: 0, page_errors: 0, http_errors: [] };
    result.browsers.push(metrics);
    page.on('pageerror', () => metrics.page_errors++);
    page.on('response', r => { if (r.status() >= 400) metrics.http_errors.push({ status: r.status(), origin: new URL(r.url()).origin, path: new URL(r.url()).pathname.replace(/\/verify\/[^/]+/, '/verify/[redacted]') }); });
    page.on('websocket', ws => {
      metrics.websocket_connections++;
      ws.on('framesent', () => metrics.frames_sent++);
      ws.on('framereceived', () => metrics.frames_received++);
      ws.on('socketerror', () => metrics.websocket_errors++);
    });
    pages.push(page);
    await page.goto(result.url, { waitUntil: 'domcontentloaded' });
    await page.locator('[data-testid="editor-content"]').waitFor({ state: 'visible', timeout: 60000 });
  }
  const editor = p => p.locator('[data-testid="editor-content"]').last();
  const wsState = p => p.evaluate(() => (window.__swarmWs || []).map(({ socket, row }) => ({ ...row, readyState: socket.readyState })));
  for (const page of pages) {
    await expect.poll(async () => (await wsState(page)).some(row => row.readyState === 1), { timeout: 30000 }).toBe(true);
  }
  async function append(p, value) {
    await editor(p).click();
    await p.keyboard.press('ControlOrMeta+End');
    await p.keyboard.press('Enter');
    await p.keyboard.type(value, { delay: 25 });
  }
  const first = `${marker} From client A`;
  const second = `${marker} From client B`;
  await append(pages[0], first);
  await expect(editor(pages[1])).toContainText(first, { timeout: 30000 });
  result.checks.push({ name: 'client_A_to_B_realtime', passed: true });
  await append(pages[1], second);
  await expect(editor(pages[0])).toContainText(second, { timeout: 30000 });
  result.checks.push({ name: 'client_B_to_A_realtime', passed: true });
  const baseline = await editor(pages[0]).innerText();
  await expect.poll(() => editor(pages[1]).innerText(), { timeout: 30000 }).toBe(baseline);
  result.before_replacement = { text: baseline, websockets: await Promise.all(pages.map(wsState)) };
  for (let i = 0; i < pages.length; i++) await pages[i].screenshot({ path: path.join(root, `ui-client-${i + 1}-before.png`) });
  save('ui-replacement-ready.json', { ready: true, url: result.url, text: baseline, time: new Date().toISOString() });
  save('ui-results.json', result);
  console.log(JSON.stringify({ stage: 'ready_for_cloud_replacement', view_id: viewId, checks: result.checks }));
  // The operator replaces the local test Cloud service after readiness, waits for
  // health, then creates ui-replacement-complete in the same runtime directory.
  const deadline = Date.now() + 10 * 60_000;
  while (!fs.existsSync(path.join(root, 'ui-replacement-complete')) && Date.now() < deadline) await new Promise(r => setTimeout(r, 500));
  if (!fs.existsSync(path.join(root, 'ui-replacement-complete'))) throw new Error('Parent replacement marker timeout');
  for (const page of pages) {
    await expect.poll(async () => (await wsState(page)).some(row => row.readyState === 1), { timeout: 90000 }).toBe(true);
  }
  result.after_replacement = { websockets: await Promise.all(pages.map(wsState)) };
  const third = `${marker} After replacement`;
  await append(pages[0], third);
  await expect(editor(pages[1])).toContainText(third, { timeout: 45000 });
  result.checks.push({ name: 'reconnected_realtime_after_cloud_replacement', passed: true });
  const persisted = await editor(pages[0]).innerText();
  await Promise.all(pages.map(p => p.reload({ waitUntil: 'domcontentloaded' })));
  for (const page of pages) await expect.poll(() => editor(page).innerText(), { timeout: 60000 }).toBe(persisted);
  result.checks.push({ name: 'both_clients_reload_same_content', passed: true });
  // Fresh independent browser storage confirms server persistence, not cached Yjs.
  const clean = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const freshToken = await token();
  await clean.addInitScript(t => localStorage.setItem('token', JSON.stringify(t)), freshToken);
  const fresh = await clean.newPage();
  await fresh.goto(result.url, { waitUntil: 'domcontentloaded' });
  await expect.poll(() => editor(fresh).innerText(), { timeout: 60000 }).toBe(persisted);
  result.checks.push({ name: 'fresh_browser_context_server_persistence', passed: true });
  result.persisted_text = persisted;
  for (let i = 0; i < pages.length; i++) await pages[i].screenshot({ path: path.join(root, `ui-client-${i + 1}-after.png`) });
  await fresh.screenshot({ path: path.join(root, 'ui-fresh-context.png') });
  result.finished_at = new Date().toISOString();
  result.passed = true;
  save('ui-results.json', result);
  console.log(JSON.stringify({ stage: 'completed', passed: true, checks: result.checks }));
} catch (error) {
  result.passed = false;
  result.error = String(error.message).replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[redacted]');
  for (let i = 0; i < pages.length; i++) {
    await pages[i].screenshot({ path: path.join(root, `ui-error-${i + 1}.png`) }).catch(() => {});
    result.browsers[i].visible_text = (await pages[i].locator('body').innerText().catch(() => '')).slice(0, 8000);
  }
  save('ui-results.json', result);
  console.error(JSON.stringify({ passed: false, error: result.error }));
  process.exitCode = 1;
} finally {
  await browser.close();
}
