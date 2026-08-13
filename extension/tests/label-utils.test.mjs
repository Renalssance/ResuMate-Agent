import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { findElementLabel, nearbyTextFor } = require('../content/label-utils.js');

function node(text = '', children = []) {
  const element = {
    textContent: text,
    children,
    parentElement: null,
    previousElementSibling: null,
    tagName: 'DIV',
    getAttribute() {
      return '';
    },
    closest() {
      return null;
    },
  };
  children.forEach((child, index) => {
    child.parentElement = element;
    child.previousElementSibling = children[index - 1] || null;
  });
  return element;
}

function input() {
  return {
    textContent: '',
    children: [],
    parentElement: null,
    previousElementSibling: null,
    tagName: 'INPUT',
    id: '',
    getAttribute() {
      return '';
    },
    closest() {
      return null;
    },
  };
}

function rectElement(text, rect) {
  return {
    textContent: text,
    children: [],
    parentElement: null,
    previousElementSibling: null,
    tagName: 'DIV',
    getBoundingClientRect() {
      return rect;
    },
    getAttribute() {
      return '';
    },
    querySelector() {
      return null;
    },
    closest() {
      return null;
    },
  };
}

{
  const field = input();
  node('', [node('项目名称'), node('', [field])]);

  assert.equal(findElementLabel(field), '项目名称');
  assert.equal(nearbyTextFor(field), '项目名称');
}

{
  const field = input();
  node('', [node('起止时间'), node('', [field]), node('-'), node('', [input()])]);

  assert.equal(findElementLabel(field), '起止时间');
}

{
  const field = input();
  field.getBoundingClientRect = () => ({ left: 360, right: 760, top: 140, bottom: 180, width: 400, height: 40 });
  const label = rectElement('项目名称', { left: 360, right: 430, top: 110, bottom: 132, width: 70, height: 22 });
  const unrelated = rectElement('首页', { left: 20, right: 60, top: 10, bottom: 30, width: 40, height: 20 });
  globalThis.document = {
    querySelectorAll(selector) {
      assert.equal(selector, 'body *');
      return [unrelated, label];
    },
    getElementById() {
      return null;
    },
  };
  globalThis.getComputedStyle = () => ({ display: 'block', visibility: 'visible', opacity: '1' });

  assert.equal(findElementLabel(field), '项目名称');

  delete globalThis.document;
  delete globalThis.getComputedStyle;
}
