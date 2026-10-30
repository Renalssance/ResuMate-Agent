import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../../../frontend/package.json', import.meta.url));
const { JSDOM } = require('jsdom');
let sequence = 0;
export async function until(condition, message = 'side panel update') {
  for (let i = 0; i < 60; i++) { if (condition()) return; await new Promise(resolve => setImmediate(resolve)); }
  throw new Error(`Timed out waiting for ${message}`);
}
export async function sidepanel({ profiles = [], handle } = {}) {
  const html = await readFile(new URL('../../sidepanel/sidepanel.html', import.meta.url), 'utf8');
  const dom = new JSDOM(html, { url: 'chrome-extension://resumate-test/sidepanel/sidepanel.html' });
  globalThis.document = dom.window.document;
  globalThis.window = dom.window;
  const messages = [], contentMessages = [], stored = {}, listeners = {};
  let tab = { id: 7, url: 'https://jobs.example/Job?ref=1#detail', title: 'Current job' };
  const elements = [{ index: 0, tag: 'textarea', labelText: 'Work experience' }, { index: 1, tag: 'input', labelText: 'Name' }];
  globalThis.chrome = {
    runtime: { sendMessage: async request => {
      messages.push(request);
      if (handle) { const answer = await handle(request); if (answer !== undefined) return answer; }
      switch (request.type) {
        case 'GET_SESSION': return { ok: true, data: { apiBase: 'http://localhost:8000', authenticated: true, username: 'Ada' } };
        case 'LIST_PROFILES': return { ok: true, data: profiles };
        case 'GET_PROFILE': return { ok: true, data: profiles.find(item => item.id === request.payload.profileId) };
        case 'RECORD_EVENT': return { ok: true, data: { ok: true } };
        case 'MATCH_FIELDS': {
          const profile = profiles.find(item => item.id === request.payload.profileId);
          return { ok: true, data: { matches: profile.sections[0].fields.map((field, i) => ({ fieldKey: field.key, elementIndex: i, field, element: elements[i], reason: 'label' })), blocked: [] } };
        }
        default: return { ok: false, error: { message: 'unimplemented test message' } };
      }
    } },
    i18n: { getUILanguage: () => 'zh-CN' },
    storage: { local: {
      get: async keys => Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(key => [key, stored[key]])),
      set: async values => Object.assign(stored, values)
    } },
    scripting: { executeScript: async () => [{ result: { url: tab.url, title: tab.title } }] },
    tabs: {
      query: async () => [tab], get: async () => tab,
      sendMessage: async (tabId, request) => { contentMessages.push({ tabId, ...request }); return request.type === 'SCAN_FORM' ? { elements } : { results: request.items.map(() => ({ success: true })) }; },
      onUpdated: { addListener: fn => { listeners.updated = fn; } },
      onActivated: { addListener: fn => { listeners.activated = fn; } }
    }
  };
  await import(`../../sidepanel/sidepanel.js?test=${++sequence}`);
  await until(() => messages.some(item => item.type === 'LIST_PROFILES'));
  await until(() => profiles.length ? document.querySelectorAll('#profileFields .field').length : document.getElementById('statusText').dataset.rawStatus === 'status.noProfiles');
  return { dom, messages, contentMessages, stored, listeners, $: id => document.getElementById(id), navigate(url) { tab = { ...tab, url }; listeners.updated(tab.id, { url }, tab); } };
}
