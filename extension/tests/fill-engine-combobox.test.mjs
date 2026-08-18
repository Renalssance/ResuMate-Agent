import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const listeners = {};
const element = {
  tagName: 'INPUT',
  type: 'text',
  value: '',
  readOnly: true,
  disabled: false,
  isContentEditable: false,
  id: 'expectedCity',
  name: '',
  placeholder: '',
  textContent: '',
  selected: '',
  focus() {},
  click() {
    this.clicked = true;
  },
  dispatchEvent(event) {
    this.dispatched = [...(this.dispatched || []), event.type];
  },
  getAttribute(name) {
    return name === 'role' ? 'combobox' : '';
  },
  closest() {
    return null;
  },
  getBoundingClientRect() {
    return { width: 120, height: 32, left: 0, right: 120, top: 0, bottom: 32 };
  },
  scrollIntoView() {},
};

globalThis.Event = class {
  constructor(type) {
    this.type = type;
  }
};
globalThis.KeyboardEvent = globalThis.Event;
globalThis.CSS = { escape: (value) => String(value) };
globalThis.HTMLInputElement = function () {};
globalThis.HTMLInputElement.prototype = {};
globalThis.HTMLTextAreaElement = function () {};
globalThis.HTMLTextAreaElement.prototype = {};
globalThis.window = {
  getComputedStyle: () => ({ display: 'block', visibility: 'visible', opacity: '1' }),
  innerWidth: 800,
  innerHeight: 600,
};
globalThis.document = {
  addEventListener() {},
  contains: (target) => target === element,
  querySelectorAll: () => [element],
  querySelector: () => null,
  documentElement: { clientWidth: 800, clientHeight: 600 },
};
globalThis.chrome = {
  runtime: {
    onMessage: {
      addListener(listener) {
        listeners.message = listener;
      },
    },
  },
};

const require = createRequire(import.meta.url);
require('../content/fill-engine.js');

let scan = null;
listeners.message({ type: 'SCAN_FORM' }, null, (response) => {
  scan = response;
});

assert.equal(scan.elements.length, 1);
assert.equal(scan.elements[0].tag, 'input');

let fill = null;
listeners.message({ type: 'FILL_SELECTED', items: [{ elementIndex: 0, value: '上海' }] }, null, (response) => {
  fill = response;
});

assert.equal(fill.results[0].success, true);
assert.equal(element.value, '上海');
assert.deepEqual(element.dispatched, ['input', 'change', 'keydown']);
