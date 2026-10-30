import assert from 'node:assert/strict';
import test from 'node:test';
import { sidepanel, until } from './helpers/sidepanel.mjs';
import { STORAGE_KEYS as K } from '../lib/constants.js';

const profile = (id, value, sourceKind = 'resume') => ({ id, name: 'Ada', sourceKind, sourceResumeId: 'resume:1', resumeVersionId: sourceKind === 'resume_version' ? id.slice(8) : null, revision: sourceKind === 'resume_version' ? 3 : null, jdId: null, updatedAt: '2026-10-30T09:30:00Z', fieldCount: 2, sections: [{ id: 'work', fields: [{ key: 'work.0.description', label: 'Work experience', value }, { key: 'name', label: 'Name', value: 'Ada' }] }] });
const profiles = [profile('resume:1', 'Original work'), profile('version:first-id', 'Version one', 'resume_version'), profile('version:second-id', 'Version two', 'resume_version')];
async function choose(panel, id) {
  panel.$('profileSelect').value = id;
  panel.$('profileSelect').dispatchEvent(new panel.dom.window.Event('change'));
  await until(() => panel.$('profileFields').textContent.includes(profiles.find(item => item.id === id).sections[0].fields[0].value));
}
async function scan(panel) {
  panel.$('scanBtn').click();
  await until(() => panel.$('matches').querySelectorAll('input').length === 2);
}

test('same-name confirmed versions show source, revision, creation date and distinct existing IDs', async () => {
  const panel = await sidepanel({ profiles });
  const labels = [...panel.$('profileSelect').options].map(item => item.textContent);
  assert.match(labels[0], /原简历/);
  assert.match(labels[1], /已确认版本.*第 3 版.*创建/);
  assert.match(labels[1], /first-id/); assert.match(labels[2], /second-id/);
  assert.notEqual(labels[1], labels[2]);
  panel.dom.window.close();
});

test('switching original to two versions clears review; fill sends only selected preview values', async () => {
  const panel = await sidepanel({ profiles });
  await scan(panel);
  for (const id of ['version:first-id', 'version:second-id']) {
    await choose(panel, id);
    assert.equal(panel.$('fillBtn').disabled, true);
    assert.equal(panel.$('matches').querySelectorAll('input').length, 0);
    await scan(panel);
    const online = panel.messages.filter(item => item.type === 'MATCH_FIELDS').at(-1).payload;
    assert.equal(online.profileId, id); assert.equal('profile' in online, false);
  }
  const unchecked = panel.$('matches').querySelectorAll('input')[1];
  unchecked.checked = false; unchecked.dispatchEvent(new panel.dom.window.Event('change'));
  panel.$('fillBtn').click();
  await until(() => panel.contentMessages.some(item => item.type === 'FILL_SELECTED'));
  assert.deepEqual(panel.contentMessages.find(item => item.type === 'FILL_SELECTED').items, [{ elementIndex: 0, value: 'Version two' }]);
  assert.equal(panel.contentMessages.some(item => /SUBMIT|APPLICATION/.test(item.type)), false);
  panel.dom.window.close();
});

test('offline refresh retains selected loaded version and its metadata', async () => {
  let offline = false;
  const panel = await sidepanel({ profiles, handle: ({ type }) => type === 'LIST_PROFILES' && offline ? { ok: false, error: { message: 'offline' } } : undefined });
  await choose(panel, 'version:second-id');
  panel.stored[K.profiles] = profiles;
  offline = true; panel.$('refreshProfilesBtn').click();
  await until(() => panel.$('statusText').dataset.rawStatus === 'Offline' || panel.$('statusText').dataset.rawStatus === 'status.profileRefreshed');
  // Wait for the stored-cache fallback to render, rather than the immediate stale-scan status.
  await until(() => panel.$('profileSummary').textContent.includes('缓存'));
  assert.equal(panel.$('profileSelect').value, 'version:second-id');
  assert.match(panel.$('profileSelect').selectedOptions[0].textContent, /已确认版本.*second-id/);
  assert.match(panel.$('profileSummary').textContent, /缓存版本/);
  panel.dom.window.close();
});

for (const phase of ['LIST_PROFILES', 'GET_PROFILE']) {
  test(`late A ${phase} response cannot overwrite B after logout/login`, async () => {
    let owner = 'A', pending = false, release;
    const panel = await sidepanel({ profiles, handle: async ({ type, payload }) => {
      if (type === 'GET_SESSION') return { ok: true, data: { apiBase: 'http://localhost:8000', authenticated: true, username: owner } };
      if (type === 'SAVE_SETTINGS') return { ok: true, data: { apiBase: payload.apiBase, authenticated: Boolean(owner), username: owner } };
      if (type === 'AUTH_LOGOUT') { owner = ''; return { ok: true, data: { apiBase: 'http://localhost:8000', authenticated: false, username: '' } }; }
      if (type === 'AUTH_LOGIN') { owner = payload.username; return { ok: true, data: { apiBase: 'http://localhost:8000', authenticated: true, username: owner } }; }
      if (pending && type === phase && owner === 'A') return new Promise(resolve => { release = resolve; });
      if (owner === 'B' && type === 'LIST_PROFILES') return { ok: true, data: [profile('resume:B', 'B work')] };
      if (owner === 'B' && type === 'GET_PROFILE') return { ok: true, data: profile('resume:B', 'B work') };
    } });
    pending = true; panel.$('refreshProfilesBtn').click();
    await until(() => release);
    panel.$('logoutBtn').click(); await until(() => panel.$('authStatus').textContent === '未登录');
    panel.$('usernameInput').value = 'B'; panel.$('passwordInput').value = 'b'; panel.$('loginBtn').click();
    await until(() => panel.$('profileFields').textContent.includes('B work'));
    release({ ok: true, data: phase === 'LIST_PROFILES' ? [profile('resume:A', 'A late')] : profile('resume:A', 'A late') });
    for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve));
    assert.equal(panel.$('profileSelect').value, 'resume:B');
    assert.match(panel.$('profileFields').textContent, /B work/);
    assert.doesNotMatch(panel.$('profileFields').textContent, /A late/);
    panel.dom.window.close();
  });
}

test('current account 401 clears displayed fields and requests login instead of staying busy', async () => {
  let expired = false;
  const panel = await sidepanel({ profiles, handle: ({ type }) => type === 'LIST_PROFILES' && expired ? { ok: false, error: { status: 401, message: 'expired' } } : undefined });
  expired = true; panel.$('refreshProfilesBtn').click();
  await until(() => panel.$('authStatus').textContent === '未登录');
  assert.equal(panel.$('profileSelect').options.length, 0);
  assert.equal(panel.$('fillBtn').disabled, true);
  assert.equal(panel.$('statusText').dataset.rawStatus, 'auth.loginRequired');
  panel.dom.window.close();
});
