import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { sidepanel, until } from './helpers/sidepanel.mjs';
const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const { JSDOM } = require('jsdom');

async function capture(html) {
  const dom = new JSDOM(html, { url: 'https://jobs.example/Job?ref=1#detail' });
  const source = await readFile(new URL('../content/job-capture.js', import.meta.url), 'utf8');
  const result = vm.runInNewContext(source, { document: dom.window.document, window: dom.window, location: dom.window.location, fetch: () => assert.fail('capture must not fetch'), chrome: { storage: new Proxy({}, { get() { assert.fail('capture must not access storage'); } }) } });
  dom.window.close();
  return result;
}

test('capture keeps visible main paragraphs and full URL, excludes hidden/control/navigation content', async () => {
  const result = await capture(`<title>Engineer — Careers</title><nav>navigation bait</nav><main><h1>Platform Engineer</h1><p>Build services.</p><p>Review systems <strong>with peers</strong>.</p><p style="margin-top:2000px">Read below the fold.</p><div hidden>hidden bait</div><div style="display:none">display bait</div><div style="visibility:hidden">visibility bait</div><div aria-hidden="true">aria bait</div><input value="private input"><textarea>private textarea</textarea><select><option>private choice</option></select><script>secret JSON</script><footer>footer bait</footer></main>`);
  assert.equal(result.title, 'Platform Engineer');
  assert.equal(result.sourceUrl, 'https://jobs.example/Job?ref=1#detail');
  assert.match(result.text, /Build services\.\nReview systems with peers\./);
  assert.match(result.text, /Read below the fold/);
  assert.doesNotMatch(result.text, /bait|private|secret/);
});

test('capture falls back to visible article/body and does not read hidden main ancestors', async () => {
  const article = await capture('<div hidden><main>hidden main bait</main></div><article><p>Real article.</p></article><footer>footer bait</footer>');
  assert.equal(article.text, 'Real article.');
  const body = await capture('<nav>navigation bait</nav><h1>Researcher</h1><div>Body description.</div><button>Apply now</button>');
  assert.equal(body.text, 'Researcher\nBody description.');
});

test('click reads editable snapshot; save uses edits and repeat save reports existing source', async () => {
  let saves = 0;
  const panel = await sidepanel({ handle: async ({ type, payload }) => {
    if (type === 'CAPTURE_JOB_PAGE') return { ok: true, data: { title: 'Engineer', company: 'Example', text: 'Original description', sourceUrl: 'https://jobs.example/Job?ref=1#detail' } };
    if (type === 'SAVE_JOB') return { ok: true, data: { job: { id: 42, ...payload }, created: ++saves === 1 } };
  } });
  assert.ok(panel.$('captureJobBtn'), 'capture action is available');
  assert.equal(panel.messages.some(item => item.type === 'CAPTURE_JOB_PAGE'), false);
  panel.$('captureJobBtn').click();
  await until(() => panel.$('jobTextInput').value === 'Original description');
  panel.$('jobTitleInput').value = 'Edited engineer'; panel.$('jobTextInput').value = 'Edited body';
  panel.$('saveJobBtn').click();
  await until(() => panel.$('jobCaptureStatus').textContent.includes('已收藏'));
  const saved = panel.messages.find(item => item.type === 'SAVE_JOB').payload;
  assert.deepEqual(saved, { title: 'Edited engineer', company: 'Example', text: 'Edited body', sourceUrl: 'https://jobs.example/Job?ref=1#detail' });
  assert.equal(panel.contentMessages.length, 0, 'capture/save does not scan, fill or submit');
  panel.$('saveJobBtn').click();
  await until(() => panel.$('jobCaptureStatus').textContent.includes('该来源已收藏'));
  panel.navigate('https://jobs.example/Other');
  assert.equal(panel.$('jobTextInput').value, ''); assert.equal(panel.$('jobUrlInput').value, '');
  panel.dom.window.close();
});

test('injection failure leaves paste fallback and missing title/body cannot save', async () => {
  const panel = await sidepanel({ handle: async ({ type, payload }) => {
    if (type === 'CAPTURE_JOB_PAGE') return { ok: false, error: { message: 'Cannot access this page' } };
    if (type === 'SAVE_JOB') return { ok: true, data: { job: { id: 43, ...payload }, created: true } };
  } });
  assert.ok(panel.$('captureJobBtn'), 'capture action is available');
  panel.$('captureJobBtn').click();
  await until(() => panel.$('jobCaptureStatus').textContent.includes('粘贴'));
  panel.$('saveJobBtn').click();
  assert.equal(panel.messages.some(item => item.type === 'SAVE_JOB'), false);
  panel.$('jobTitleInput').value = 'Manual title'; panel.$('jobTextInput').value = 'Pasted job'; panel.$('jobUrlInput').value = '';
  panel.$('saveJobBtn').click();
  await until(() => panel.$('jobCaptureStatus').textContent.includes('已收藏'));
  assert.equal(panel.messages.find(item => item.type === 'SAVE_JOB').payload.sourceUrl, '');
  panel.dom.window.close();
});

for (const [sourceKind, sourceResumeId, expectedResumeId] of [
  ['resume', 'resume:1', 1],
  ['resume_version', 'resume:7', 7],
  ['resume_version', '', undefined]
]) {
  test(`save associates ${sourceKind} with source ${sourceResumeId || 'deleted source'} using the actual profile contract`, async () => {
    const profile = { id: sourceKind === 'resume' ? 'resume:1' : 'version:confirmed', name: 'Ada', sourceKind, sourceResumeId, resumeVersionId: sourceKind === 'resume_version' ? 'confirmed' : null, revision: 3, updatedAt: '2026-10-30T09:30:00Z', sections: [{ fields: [{ key: 'name', label: 'Name', value: 'Ada' }] }] };
    const panel = await sidepanel({ profiles: [profile], handle: async ({ type, payload }) => type === 'SAVE_JOB' ? { ok: true, data: { job: { id: 44, ...payload }, created: true } } : undefined });
    panel.$('jobTitleInput').value = 'Saved job'; panel.$('jobTextInput').value = 'Pasted description';
    panel.$('saveJobBtn').click();
    await until(() => panel.messages.some(item => item.type === 'SAVE_JOB'));
    const payload = panel.messages.find(item => item.type === 'SAVE_JOB').payload;
    assert.equal(payload.primaryResumeId, expectedResumeId);
    assert.equal(Object.hasOwn(payload, 'primaryResumeId'), expectedResumeId !== undefined);
    await until(() => !panel.$('saveJobBtn').disabled);
    panel.dom.window.close();
  });
}
