import assert from 'node:assert/strict';
import test from 'node:test';
import { STORAGE_KEYS as K } from '../lib/constants.js';

let sequence = 0;
async function background(seed = {}) {
  const stored = { ...seed }, calls = [], access = [];
  let listener;
  globalThis.chrome = {
    runtime: { id: 'resumate-test', getURL: path => `chrome-extension://resumate-test/${path}`, onMessage: { addListener: fn => { listener = fn; } } },
    sidePanel: { setPanelBehavior: async () => {} },
    storage: { local: {
      get: async keys => Object.fromEntries((Array.isArray(keys) ? keys : [keys]).map(key => [key, stored[key]])),
      set: async value => Object.assign(stored, value),
      remove: async keys => keys.forEach(key => delete stored[key]),
      setAccessLevel: async value => access.push(value)
    } },
    tabs: { query: async () => [{ id: 7, url: 'https://jobs.example/Job?ref=1#detail' }] },
    scripting: { executeScript: async () => [] }
  };
  let respond = (url, init) => {
    if (url.endsWith('/auth/login')) {
      const { username } = JSON.parse(init.body);
      return { access_token: `token-${username}`, username };
    }
    if (url.includes('/api/autofill/profiles/')) return { id: 'resume:1', name: 'A resume', sections: [] };
    return [];
  };
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    const data = await respond(url, init);
    return data instanceof Response ? data : new Response(JSON.stringify(data), { status: 200 });
  };
  await import(`../service-worker.js?test=${++sequence}`);
  const sender = { id: chrome.runtime.id, url: chrome.runtime.getURL('sidepanel/sidepanel.html'), tab: { id: 19 } };
  return {
    stored, calls, access, sender,
    respond: fn => { respond = fn; },
    message(type, payload, from = sender) {
      assert.equal(typeof listener, 'function', 'worker registers a real runtime message listener');
      return new Promise(resolve => {
        const keepAlive = listener({ type, payload }, from, resolve);
        assert.equal(keepAlive, true, 'async replies keep the message channel alive');
      });
    }
  };
}

test('only the exact own side panel can log in; UI session never contains a token', async () => {
  const worker = await background();
  const result = await worker.message('AUTH_LOGIN', { username: 'A', password: 'only-once' });
  assert.deepEqual(result, { ok: true, data: { apiBase: 'http://127.0.0.1:8000', authenticated: true, username: 'A' } });
  assert.equal(worker.stored[K.authToken], 'token-A');
  assert.equal(JSON.stringify(result).includes('token-A'), false);
  assert.equal(JSON.stringify(worker.stored).includes('only-once'), false);
  assert.deepEqual(worker.access, [{ accessLevel: 'TRUSTED_CONTEXTS' }]);
  assert.deepEqual((await worker.message('GET_SESSION')).data, result.data);
});

test('unknown, content-script, foreign and malformed messages never fetch', async () => {
  const worker = await background();
  for (const [type, payload, sender] of [
    ['FETCH', { url: 'https://elsewhere.example', method: 'POST' }],
    ['AUTH_LOGIN', { username: 'A', password: 'x' }, { id: 'resumate-test', url: 'https://jobs.example', tab: { id: 7 } }],
    ['AUTH_LOGIN', { username: 'A', password: 'x' }, { id: 'other-extension', url: worker.sender.url }],
    ['AUTH_LOGIN', { username: ['A'], password: 'x' }],
    ['GET_PROFILE', { profileId: 12 }],
    ['MATCH_FIELDS', { profileId: 'version:1', page: {}, elements: 'bad' }],
    ['SAVE_SETTINGS', { apiBase: 42 }]
  ]) {
    const reply = await worker.message(type, payload, sender || worker.sender);
    assert.equal(reply.ok, false);
    assert.equal(typeof reply.error.message, 'string');
  }
  assert.equal(worker.calls.length, 0);
});

test('A loaded cache is removed on logout; B offline refresh cannot recover A', async () => {
  const worker = await background();
  await worker.message('AUTH_LOGIN', { username: 'A', password: 'a' });
  await worker.message('GET_PROFILE', { profileId: 'resume:1' });
  assert.equal(worker.stored[K.profiles][0].name, 'A resume');
  worker.stored[K.activeProfileId] = 'resume:1'; worker.stored[K.lastMatches] = ['old'];
  await worker.message('AUTH_LOGOUT');
  for (const key of [K.authToken, K.username, K.profiles, K.activeProfileId, K.lastMatches]) assert.equal(worker.stored[key], undefined);
  await worker.message('AUTH_LOGIN', { username: 'B', password: 'b' });
  worker.respond(() => { throw new Error('offline'); });
  assert.equal((await worker.message('LIST_PROFILES')).ok, false);
  assert.equal(worker.stored[K.profiles], undefined);
  assert.equal(worker.stored[K.authToken], 'token-B');
});

test('login, backend changes and 401 clear old cache, while network loss preserves it', async () => {
  const worker = await background({ [K.profiles]: [{ id: 'resume:old' }], [K.activeProfileId]: 'resume:old', [K.lastMatches]: ['old'] });
  await worker.message('AUTH_LOGIN', { username: 'A', password: 'a' });
  assert.equal(worker.stored[K.profiles], undefined);
  await worker.message('GET_PROFILE', { profileId: 'resume:1' });
  worker.respond(() => { throw new Error('network down'); });
  assert.equal((await worker.message('LIST_PROFILES')).ok, false);
  assert.equal(worker.stored[K.profiles].length, 1);
  worker.respond(() => new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }));
  const expired = await worker.message('LIST_PROFILES');
  assert.equal(expired.error.status, 401);
  assert.equal(worker.stored[K.profiles], undefined);
  assert.equal(worker.stored[K.authToken], undefined);
  Object.assign(worker.stored, { [K.authToken]: 'another', [K.profiles]: [{}], [K.activeProfileId]: 'resume:1', [K.lastMatches]: ['old'] });
  const changed = await worker.message('SAVE_SETTINGS', { apiBase: 'http://localhost:9000' });
  assert.equal(changed.data.authenticated, false);
  for (const key of [K.authToken, K.profiles, K.activeProfileId, K.lastMatches]) assert.equal(worker.stored[key], undefined);
});

export { background };

test('capture is click-only scripting and save uses the explicit jobs capture endpoint', async () => {
  const worker = await background({ [K.authToken]: 'token-A' });
  const scripts = [];
  chrome.scripting.executeScript = async request => {
    scripts.push(request);
    return [{ result: request.files[0] === 'content/scraper.js' ? { position: 'metadata title', company: 'Company' } : { title: 'Visible title', text: 'Visible body', sourceUrl: 'https://jobs.example/Job?ref=1#detail' } }];
  };
  assert.equal(scripts.length, 0);
  const captured = await worker.message('CAPTURE_JOB_PAGE');
  assert.deepEqual(captured.data, { title: 'Visible title', company: 'Company', text: 'Visible body', sourceUrl: 'https://jobs.example/Job?ref=1#detail' });
  assert.deepEqual(scripts.map(item => item.files[0]), ['content/scraper.js', 'content/job-capture.js']);
  assert.equal(worker.calls.length, 0);
  worker.respond((_url, init) => ({ job: { id: 1, ...JSON.parse(init.body) }, created: true }));
  const saved = await worker.message('SAVE_JOB', { ...captured.data, primaryResumeId: 1 });
  assert.equal(saved.data.created, true);
  assert.equal(worker.calls[0].url, 'http://127.0.0.1:8000/api/jobs/capture');
  assert.equal(worker.calls[0].init.headers.Authorization, 'Bearer token-A');
  const invalid = await worker.message('SAVE_JOB', { title: 'job', text: [], sourceUrl: 'https://jobs.example' });
  assert.equal(invalid.ok, false); assert.equal(worker.calls.length, 1);
});

test('late A 401 does not clear B session or B cache', async () => {
  const worker = await background();
  await worker.message('AUTH_LOGIN', { username: 'A', password: 'a' });
  let release;
  const response = new Promise(resolve => { release = resolve; });
  worker.respond(() => response);
  const old = worker.message('LIST_PROFILES');
  while (!worker.calls.some(item => item.url.endsWith('/profiles'))) await new Promise(resolve => setImmediate(resolve));
  await worker.message('AUTH_LOGOUT');
  worker.respond(() => ({ access_token: 'token-B', username: 'B' }));
  await worker.message('AUTH_LOGIN', { username: 'B', password: 'b' });
  worker.stored[K.profiles] = [{ id: 'resume:B' }];
  release(new Response(JSON.stringify({ detail: 'A expired' }), { status: 401 }));
  assert.equal((await old).error.status, 401);
  assert.equal(worker.stored[K.authToken], 'token-B');
  assert.equal(worker.stored[K.profiles][0].id, 'resume:B');
});

test('late A list result is not delivered as B data', async () => {
  const worker = await background({ [K.authToken]: 'token-A', [K.username]: 'A' });
  let release;
  worker.respond(() => new Promise(resolve => { release = resolve; }));
  const old = worker.message('LIST_PROFILES');
  while (!release) await new Promise(resolve => setImmediate(resolve));
  await worker.message('AUTH_LOGOUT');
  worker.respond(() => ({ access_token: 'token-B', username: 'B' }));
  await worker.message('AUTH_LOGIN', { username: 'B', password: 'b' });
  release([{ id: 'resume:A' }]);
  const stale = await old;
  assert.equal(stale.ok, false);
  assert.match(stale.error.message, /Account changed/);
});

test('online matching forwards only the chosen server profile ID, never cached profile data', async () => {
  const worker = await background({ [K.authToken]: 'token-A' });
  await worker.message('MATCH_FIELDS', { profileId: 'version:frozen', page: { url: 'https://jobs.example' }, elements: [{ index: 0, tag: 'textarea' }], profile: { name: 'stale cached resume' } });
  assert.deepEqual(JSON.parse(worker.calls[0].init.body), { profileId: 'version:frozen', page: { url: 'https://jobs.example' }, elements: [{ index: 0, tag: 'textarea' }] });
});
