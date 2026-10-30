import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { matchLocally } from '../lib/field-matcher.js';
const require = createRequire(new URL('../../frontend/package.json', import.meta.url));
const { JSDOM } = require('jsdom');

test('real application DOM keeps nearby text within each field and protects only the actual captcha', async () => {
  const html = await readFile(new URL('../fixtures/application-form.html', import.meta.url), 'utf8');
  const dom = new JSDOM(html, { url: 'https://jobs.example/apply', runScripts: 'outside-only' });
  const { window } = dom;
  let listener;
  window.chrome = { runtime: { id: 'resumate-test', getURL: path => `chrome-extension://resumate-test/${path}`, onMessage: { addListener: fn => { listener = fn; } } } };
  // jsdom has no layout; expose ordinary rendered input boxes while using the real DOM/labels.
  window.Element.prototype.getBoundingClientRect = () => ({ width: 240, height: 34, left: 0, right: 240, top: 0, bottom: 34 });
  const style = window.document.createElement('style');
  style.textContent = 'input, textarea, select { opacity: 1; visibility: visible; }';
  window.document.head.append(style);
  for (const file of ['label-utils.js', 'fill-engine.js']) window.eval(await readFile(new URL(`../content/${file}`, import.meta.url), 'utf8'));
  let scan;
  listener({ type: 'SCAN_FORM' }, { id: window.chrome.runtime.id, url: window.chrome.runtime.getURL('sidepanel/sidepanel.html') }, response => { scan = response; });
  assert.equal(scan.elements.length, 9);
  const name = scan.elements.find(element => element.name === 'candidate_name');
  const work = scan.elements.find(element => element.name === 'work_description');
  const captcha = scan.elements.find(element => element.name === 'captcha');
  assert.equal(name.nearbyText, '姓名');
  assert.equal(work.nearbyText, '工作职责');
  assert.equal(captcha.nearbyText, '验证码');
  const result = matchLocally({ sections: [{ fields: [
    { key: 'candidate_name', label: 'Name', value: 'Ada', aliases: ['姓名'] },
    { key: 'work_experience.0.description', label: 'Work Description', value: 'Frozen work', aliases: ['工作职责'] }
  ] }] }, scan.elements);
  assert.deepEqual(result.matches.map(match => match.element.name), ['candidate_name', 'work_description']);
  assert.deepEqual(result.blocked.map(blocked => blocked.element.name), ['captcha']);
  dom.window.close();
});
