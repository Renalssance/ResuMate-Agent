(function (root) {
  'use strict';

  const CONTROL_TAGS = new Set(['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON', 'OPTION']);
  const MAX_TEXT_LENGTH = 160;

  function cleanText(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function textOf(element, limit = MAX_TEXT_LENGTH) {
    return cleanText(element && element.textContent).slice(0, limit);
  }

  function isControl(element) {
    return element && CONTROL_TAGS.has(String(element.tagName || '').toUpperCase());
  }

  function siblingLabel(element) {
    let current = element;
    for (let depth = 0; current && current.parentElement && depth < 4; depth += 1) {
      let sibling = current.previousElementSibling;
      for (let seen = 0; sibling && seen < 4; seen += 1) {
        const text = textOf(sibling);
        if (text) return text;
        sibling = sibling.previousElementSibling;
      }
      current = current.parentElement;
    }
    return '';
  }

  function textFromContainer(element) {
    let current = element ? element.parentElement : null;
    for (let depth = 0; current && depth < 5; depth += 1) {
      const childTexts = Array.from(current.children || [])
        .filter((child) => child !== element && !isControl(child))
        .map((child) => textOf(child, 80))
        .filter(Boolean);
      const joined = cleanText(childTexts.join(' '));
      if (joined) return joined.slice(0, MAX_TEXT_LENGTH);
      current = current.parentElement;
    }
    return '';
  }

  function rectOf(element) {
    if (!element || !element.getBoundingClientRect) return null;
    const rect = element.getBoundingClientRect();
    if (!rect || rect.width <= 0 || rect.height <= 0) return null;
    return rect;
  }

  function isVisible(element) {
    if (!element) return false;
    if (root.getComputedStyle) {
      const style = root.getComputedStyle(element);
      if (!style || style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
    }
    return Boolean(rectOf(element));
  }

  function hasControlDescendant(element) {
    return Boolean(element && element.querySelector && element.querySelector('input, textarea, select, [contenteditable]'));
  }

  function spatialLabel(element) {
    const targetRect = rectOf(element);
    if (!targetRect || !root.document || !root.document.querySelectorAll) return '';
    const targetCenterY = (targetRect.top + targetRect.bottom) / 2;
    const candidates = [];

    for (const candidate of root.document.querySelectorAll('body *')) {
      if (candidate === element || isControl(candidate) || hasControlDescendant(candidate) || !isVisible(candidate)) continue;
      const text = textOf(candidate, 80);
      if (!text || text.length > 40) continue;
      const rect = rectOf(candidate);
      if (!rect) continue;

      const above = rect.bottom <= targetRect.top + 8 && rect.bottom >= targetRect.top - 72;
      const horizontallyAligned = rect.left <= targetRect.right && rect.right >= targetRect.left - 24;
      const leftSide = rect.right <= targetRect.left + 8 && rect.right >= targetRect.left - 180 && Math.abs(((rect.top + rect.bottom) / 2) - targetCenterY) <= 32;
      if (!((above && horizontallyAligned) || leftSide)) continue;

      const horizontalGap = above ? Math.abs(rect.left - targetRect.left) : Math.abs(targetRect.left - rect.right);
      const verticalGap = above ? Math.abs(targetRect.top - rect.bottom) : Math.abs(targetCenterY - ((rect.top + rect.bottom) / 2));
      candidates.push({ text, score: verticalGap * 2 + horizontalGap });
    }

    candidates.sort((left, right) => left.score - right.score);
    return candidates[0] ? candidates[0].text : '';
  }

  function ariaLabelledBy(element) {
    const ids = cleanText(element && element.getAttribute && element.getAttribute('aria-labelledby'));
    if (!ids || !root.document || !root.document.getElementById) return '';
    return ids
      .split(/\s+/)
      .map((id) => textOf(root.document.getElementById(id), 80))
      .filter(Boolean)
      .join(' ')
      .slice(0, MAX_TEXT_LENGTH);
  }

  function nativeLabel(element) {
    if (!element) return '';
    if (element.id && root.document && root.document.querySelector && root.CSS && root.CSS.escape) {
      const label = root.document.querySelector(`label[for="${root.CSS.escape(element.id)}"]`);
      if (label) return textOf(label);
    }
    const wrapper = element.closest ? element.closest('label') : null;
    return wrapper ? textOf(wrapper) : '';
  }

  function findElementLabel(element) {
    return (
      nativeLabel(element) ||
      ariaLabelledBy(element) ||
      cleanText(element && element.getAttribute && element.getAttribute('aria-label')) ||
      siblingLabel(element) ||
      spatialLabel(element) ||
      textFromContainer(element)
    );
  }

  function nearbyTextFor(element) {
    const parts = [];
    for (const value of [findElementLabel(element), textFromContainer(element)]) {
      if (value && !parts.includes(value)) parts.push(value);
    }
    return cleanText(parts.join(' ')).slice(0, MAX_TEXT_LENGTH);
  }

  const api = {
    cleanText,
    findElementLabel,
    nearbyTextFor,
    spatialLabel,
    textOf
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.ResuMateLabelUtils = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : window);
