(function (root) {
  'use strict';

  function viewportSize() {
    const doc = root.document && root.document.documentElement ? root.document.documentElement : {};
    return {
      width: root.innerWidth || doc.clientWidth || 0,
      height: root.innerHeight || doc.clientHeight || 0
    };
  }

  function isHiddenByAttributes(element) {
    return Boolean(
      !element ||
      element.getAttribute('aria-hidden') === 'true' ||
      (element.closest && element.closest('[aria-hidden="true"]'))
    );
  }

  function isDisabledOrReadonly(element) {
    const tag = String(element && element.tagName || '').toUpperCase();
    if ((tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') && element.disabled) return true;
    return (tag === 'INPUT' || tag === 'TEXTAREA') && element.readOnly;
  }

  function hasVisibleStyle(element) {
    const getStyle = root.getComputedStyle || (root.window && root.window.getComputedStyle);
    if (!getStyle) return true;
    const style = getStyle(element);
    return Boolean(style && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity) !== 0);
  }

  function hasUsableBox(element) {
    if (!element || !element.getBoundingClientRect) return false;
    const rect = element.getBoundingClientRect();
    return Boolean(rect && rect.width >= 20 && rect.height >= 10);
  }

  function intersectsViewport(element) {
    if (!element || !element.getBoundingClientRect) return false;
    const rect = element.getBoundingClientRect();
    const viewport = viewportSize();
    return rect.right > 0 && rect.bottom > 0 && rect.left < viewport.width && rect.top < viewport.height;
  }

  function isRenderableFillTarget(element, options = {}) {
    if (isHiddenByAttributes(element) || isDisabledOrReadonly(element) || !hasVisibleStyle(element) || !hasUsableBox(element)) {
      return false;
    }
    return options.requireViewport ? intersectsViewport(element) : true;
  }

  function scrollIntoViewIfNeeded(element) {
    if (!element || !element.scrollIntoView || intersectsViewport(element)) return;
    element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' });
  }

  const api = {
    intersectsViewport,
    isRenderableFillTarget,
    scrollIntoViewIfNeeded
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  } else {
    root.ResuMateVisibilityUtils = api;
  }
})(typeof globalThis !== 'undefined' ? globalThis : window);
