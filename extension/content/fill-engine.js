(function () {
  'use strict';

  let lastFocusedElement = null;
  let scannedElements = [];

  document.addEventListener('focusin', (event) => {
    if (isFillable(event.target)) lastFocusedElement = event.target;
  }, true);

  function isFillable(element) {
    if (!element || !element.tagName) return false;
    const tag = element.tagName.toLowerCase();
    if (tag === 'input') {
      const type = (element.type || 'text').toLowerCase();
      return !['hidden', 'submit', 'button', 'reset', 'file', 'password'].includes(type);
    }
    return tag === 'textarea' || tag === 'select' || isContentEditableCandidate(element);
  }

  function isContentEditableCandidate(element) {
    const attr = element.getAttribute('contenteditable');
    return element.isContentEditable || (attr !== null && attr.toLowerCase() !== 'false');
  }

  function textOf(element) {
    return element && element.textContent ? element.textContent.trim().replace(/\s+/g, ' ').slice(0, 120) : '';
  }

  function labelFor(element) {
    if (element.id) {
      const label = document.querySelector(`label[for="${CSS.escape(element.id)}"]`);
      if (label) return textOf(label);
    }
    const wrapper = element.closest('label');
    if (wrapper) return textOf(wrapper);
    return '';
  }

  function nearbyText(element) {
    const container = element.closest('label, .form-item, .form-row, .field, .ant-form-item, .semi-form-field, .arco-form-item, div');
    return textOf(container).slice(0, 160);
  }

  function isTinyHiddenish(element) {
    const rect = element.getBoundingClientRect();
    return rect.width < 20 || rect.height < 10;
  }

  function scanForm() {
    scannedElements = [];
    const elements = [];
    const selector = 'input, textarea, select, [contenteditable]';
    document.querySelectorAll(selector).forEach((element) => {
      if (!isFillable(element)) return;
      if (isTinyHiddenish(element)) return;
      scannedElements.push(element);
      elements.push({
        index: scannedElements.length - 1,
        tag: element.tagName.toLowerCase(),
        type: element.type || '',
        id: element.id || '',
        name: element.name || '',
        placeholder: element.placeholder || '',
        labelText: labelFor(element),
        ariaLabel: element.getAttribute('aria-label') || '',
        nearbyText: nearbyText(element),
        value: element.value || ''
      });
    });
    return { elements };
  }

  function fillInput(element, value) {
    element.focus();
    const proto = element.tagName === 'INPUT' ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(element, value);
    else element.value = value;
    if (element._valueTracker) element._valueTracker.setValue(element.value);
    element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    return { success: true, filled: value };
  }

  function fillSelect(element, value) {
    element.focus();
    const search = String(value || '').toLowerCase().trim();
    let bestIndex = -1;
    for (let index = 0; index < element.options.length; index += 1) {
      const option = element.options[index];
      if (!option || option.disabled) continue;
      const text = (option.text || option.label || '').toLowerCase().trim();
      const optionValue = (option.value || '').toLowerCase().trim();
      if (text === search || optionValue === search || text.includes(search) || search.includes(text)) {
        bestIndex = index;
        break;
      }
    }
    if (bestIndex < 0) return { success: false, error: `No option for ${value}` };
    element.selectedIndex = bestIndex;
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    return { success: true, filled: element.options[bestIndex].text };
  }

  function fillContentEditable(element, value) {
    element.focus();
    element.textContent = value;
    element.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
    element.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
    return { success: true, filled: value };
  }

  function fillElement(element, value) {
    if (!element || !document.contains(element) || !isFillable(element)) {
      return { success: false, error: 'Element is no longer fillable' };
    }
    const tag = element.tagName.toLowerCase();
    if (tag === 'select') return fillSelect(element, value);
    if (tag === 'input' || tag === 'textarea') return fillInput(element, value);
    if (isContentEditableCandidate(element)) return fillContentEditable(element, value);
    return { success: false, error: `Unsupported element ${tag}` };
  }

  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (request.type === 'SCAN_FORM') {
      sendResponse(scanForm());
      return true;
    }
    if (request.type === 'FILL_SELECTED') {
      const results = (request.items || []).map((item) => {
        const element = scannedElements[item.elementIndex];
        return fillElement(element, item.value);
      });
      sendResponse({ results });
      return true;
    }
    if (request.type === 'FILL_FOCUSED') {
      sendResponse(fillElement(lastFocusedElement, request.value));
      return true;
    }
    return false;
  });
})();
