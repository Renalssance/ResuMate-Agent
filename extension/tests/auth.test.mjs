import assert from 'node:assert/strict';
import { login } from '../lib/api-client.js';
import { clearAuthSession, getSettings, saveAuthSession } from '../lib/storage.js';

function createChromeStorage(seed = {}) {
  const state = { ...seed };
  return {
    state,
    async get(keys) {
      if (Array.isArray(keys)) {
        return Object.fromEntries(keys.map((key) => [key, state[key]]));
      }
      return { [keys]: state[keys] };
    },
    async set(values) {
      Object.assign(state, values);
    },
    async remove(keys) {
      for (const key of Array.isArray(keys) ? keys : [keys]) {
        delete state[key];
      }
    },
  };
}

{
  let captured = null;
  globalThis.fetch = async (url, init) => {
    captured = { url, init };
    return new Response(
      JSON.stringify({
        access_token: 'jwt-123',
        token_type: 'bearer',
        username: 'ada',
        role: 'user',
      }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    );
  };

  const result = await login(
    { apiBase: 'http://127.0.0.1:8000' },
    { username: ' ada ', password: 'secret' },
  );

  assert.equal(captured.url, 'http://127.0.0.1:8000/auth/login');
  assert.equal(captured.init.method, 'POST');
  assert.deepEqual(JSON.parse(captured.init.body), { username: 'ada', password: 'secret' });
  assert.equal(result.accessToken, 'jwt-123');
  assert.equal(result.username, 'ada');
}

{
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ detail: 'bad credentials' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });

  await assert.rejects(
    () => login({ apiBase: 'http://127.0.0.1:8000' }, { username: 'ada', password: 'wrong' }),
    /bad credentials/,
  );
}

{
  globalThis.chrome = { storage: { local: createChromeStorage() } };

  await saveAuthSession({ token: 'jwt-123', username: 'ada', password: 'secret' });
  const settings = await getSettings();

  assert.equal(settings.token, 'jwt-123');
  assert.equal(settings.username, 'ada');
  assert.equal(globalThis.chrome.storage.local.state.resumate_password, undefined);

  await clearAuthSession();
  const cleared = await getSettings();

  assert.equal(cleared.token, '');
  assert.equal(cleared.username, '');
}
