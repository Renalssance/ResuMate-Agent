import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { isRenderableFillTarget } = require('../content/visibility-utils.js');

globalThis.window = {
  innerWidth: 1200,
  innerHeight: 800,
  getComputedStyle() {
    return { display: 'block', visibility: 'visible', opacity: '1' };
  },
};
globalThis.document = {
  documentElement: { clientWidth: 1200, clientHeight: 800 },
};

function input(rect, overrides = {}) {
  return {
    tagName: 'INPUT',
    disabled: false,
    readOnly: false,
    getAttribute(name) {
      return overrides[name] || '';
    },
    closest() {
      return null;
    },
    getBoundingClientRect() {
      return rect;
    },
    ...overrides,
  };
}

const offscreen = input({ left: 100, right: 500, top: 1800, bottom: 1840, width: 400, height: 40 });
const onscreen = input({ left: 100, right: 500, top: 200, bottom: 240, width: 400, height: 40 });
const tiny = input({ left: 100, right: 105, top: 200, bottom: 204, width: 5, height: 4 });

assert.equal(isRenderableFillTarget(offscreen, { requireViewport: false }), true);
assert.equal(isRenderableFillTarget(offscreen, { requireViewport: true }), false);
assert.equal(isRenderableFillTarget(onscreen, { requireViewport: true }), true);
assert.equal(isRenderableFillTarget(tiny, { requireViewport: false }), false);

delete globalThis.window;
delete globalThis.document;
