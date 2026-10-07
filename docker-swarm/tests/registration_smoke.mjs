// A new user completes signup and password login through the real Web UI.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(process.env.APPFLOWY_WEB_DIR || path.join(repo, 'ci'), 'package.json'));
const { chromium, expect } = require('@playwright/test');
const root = path.resolve(process.env.SWARM_TEST_DIR || path.join(repo, 'docker-swarm/.local'));
const metadata = JSON.parse(fs.readFileSync(path.join(root, 'metadata.json'), 'utf8'));
const base = (process.env.SWARM_TEST_BASE_URL || metadata.base_url).replace(/\/$/, '');
if (!['localhost', '127.0.0.1', '[::1]'].includes(new URL(base).hostname)) {
  throw new Error('Registration test requires a local deployment');
}
const marker = `WebSignup${crypto.randomBytes(6).toString('hex')}`;
const user = { email: `${marker.toLowerCase()}@example.com`, password: `Signup!1${crypto.randomBytes(20).toString('hex')}` };
const result = { started_at: new Date().toISOString(), passed: false, checks: [], browsers: [] };
const pages = [];
let browser;
function save(name, value) {
  const target = path.join(root, name);
  fs.writeFileSync(target, JSON.stringify(value, null, 2), { mode: 0o600 });
  fs.chmodSync(target, 0o600);
}
function redact(value) {
  return String(value).replaceAll(user.email, '[redacted]').replaceAll(user.password, '[redacted]')
    .replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[redacted-jwt]')
    .replace(/(https?:\/\/[^\s"'?)]+)\?[^\s"')]+/g, '$1?[redacted-query]');
}
function record(name, details = {}) {
  result.checks.push({ name, passed: true, ...details });
  save('registration-results.json', result);
  console.log(JSON.stringify({ check: name, passed: true }));
}
async function newPage() {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'en-US' });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const metrics = { page_errors: 0, http_errors: [] };
  result.browsers.push(metrics);
  pages.push(page);
  page.on('pageerror', () => metrics.page_errors++);
  page.on('response', response => {
    if (response.status() >= 400) {
      const url = new URL(response.url());
      metrics.http_errors.push({ status: response.status(), origin: url.origin,
        path: url.pathname.replace(/\/verify\/[^/]+/, '/verify/[redacted]') });
    }
  });
  return page;
}
async function workspace(page) {
  await expect(page).toHaveURL(/\/app\/[0-9a-f-]{36}(?:\/|$)/, { timeout: 60000 });
  expect(new URL(page.url()).origin).toBe(new URL(base).origin);
  await expect(page.getByTestId('sidebar-page-header')).toBeVisible({ timeout: 60000 });
  await expect(page.getByTestId('current-workspace-name')).toBeVisible();
  const id = new URL(page.url()).pathname.split('/')[2];
  await page.getByTestId('workspace-dropdown-trigger').click();
  await expect(page.getByText(user.email, { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  return id;
}

save('registration-user.json', user);
save('registration-results.json', result);
try {
  browser = await chromium.launch({ channel: process.env.SWARM_BROWSER_CHANNEL || 'chromium', headless: true });
  const page = await newPage();
  await page.goto(base + '/login', { waitUntil: 'domcontentloaded' });
  await page.getByTestId('login-create-account-button').click();
  await page.getByTestId('signup-email-input').fill(user.email);
  await page.getByTestId('signup-password-input').fill(user.password);
  await page.getByTestId('signup-confirm-password-input').fill(user.password);
  const [signup] = await Promise.all([
    page.waitForResponse(response => new URL(response.url()).pathname === '/gotrue/signup'
      && response.request().method() === 'POST'),
    page.getByTestId('signup-submit-button').click(),
  ]);
  expect(signup.ok(), 'Public signup request must succeed').toBe(true);
  const signupPayload = await signup.json();
  const account = signupPayload.user || signupPayload;
  expect(account.email).toBe(user.email);
  expect(account.id).toMatch(/^[0-9a-f-]{36}$/);
  result.user_id = account.id;
  record('public_web_password_registration');

  result.workspace_id = await workspace(page);
  record('registered_user_enters_workspace');
  const space = page.getByTestId('space-item').first();
  await expect(space).toBeVisible({ timeout: 60000 });
  await space.hover();
  await space.getByTestId('inline-add-page').first().click();
  await page.getByTestId('add-document-button').click();
  const dialog = page.getByRole('dialog').filter({ has: page.getByTestId('view-modal-close') });
  await expect(dialog).toBeVisible({ timeout: 60000 });
  const title = dialog.getByTestId('page-title-input');
  const editor = dialog.getByTestId('editor-content');
  await expect(title).toBeVisible({ timeout: 60000 });
  const titleId = await title.getAttribute('id');
  expect(titleId).toMatch(/^editor-title-[0-9a-f-]{36}$/);
  result.view_id = titleId.slice('editor-title-'.length);
  await title.fill(marker);
  await editor.click();
  const content = `${marker} created by a newly registered Web user`;
  await page.keyboard.type(content, { delay: 20 });
  await expect(editor).toContainText(content);
  record('registered_user_creates_and_edits_document');

  // This context starts without cookies, tokens, or browser storage from signup.
  const fresh = await newPage();
  await fresh.goto(base + '/login', { waitUntil: 'domcontentloaded' });
  await fresh.getByTestId('login-email-input').fill(user.email);
  await fresh.getByTestId('login-password-button').click();
  await fresh.getByTestId('password-input').fill(user.password);
  const [login] = await Promise.all([
    fresh.waitForResponse(response => new URL(response.url()).pathname === '/gotrue/token'
      && response.request().method() === 'POST'),
    fresh.getByTestId('password-submit-button').click(),
  ]);
  expect(login.ok(), 'Fresh browser password login must succeed').toBe(true);
  const loginPayload = await login.json();
  expect(loginPayload.user.id).toBe(result.user_id);
  expect(loginPayload.user.email).toBe(user.email);
  expect(await workspace(fresh)).toBe(result.workspace_id);
  record('fresh_browser_password_login_same_account');
  await fresh.goto(`${base}/app/${result.workspace_id}/${result.view_id}`, { waitUntil: 'domcontentloaded' });
  await expect(fresh.getByTestId('editor-content').last()).toContainText(content, { timeout: 60000 });
  await expect(fresh.getByTestId('page-title-input').last()).toHaveText(marker, { timeout: 30000 });
  record('registered_user_document_persists_after_fresh_login');
  result.passed = true;
  result.finished_at = new Date().toISOString();
  save('registration-results.json', result);
  console.log(JSON.stringify({ stage: 'registration_completed', passed: true, checks: result.checks }));
} catch (error) {
  result.error = redact(error.message);
  result.pages = await Promise.all(pages.map(async page => ({
    path: new URL(page.url()).pathname,
    visible_text: redact(await page.locator('body').innerText().catch(() => '')).slice(0, 5000),
  })));
  save('registration-results.json', result);
  console.error(JSON.stringify({ passed: false, error: result.error }));
  process.exitCode = 1;
} finally {
  await browser?.close();
}
