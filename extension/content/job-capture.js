(() => {
  const excluded = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'NAV', 'FOOTER', 'IFRAME', 'SVG', 'INPUT', 'TEXTAREA', 'SELECT', 'BUTTON']);
  const blocks = new Set(['P', 'DIV', 'SECTION', 'ARTICLE', 'MAIN', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'LI', 'UL', 'OL', 'TR', 'BLOCKQUOTE']);

  function visible(element) {
    for (let current = element; current; current = current.parentElement) {
      const style = window.getComputedStyle(current);
      if (current.hidden || current.getAttribute('aria-hidden') === 'true' || style.display === 'none' || ['hidden', 'collapse'].includes(style.visibility) || style.opacity === '0') return false;
    }
    return true;
  }

  function read(node) {
    if (node.nodeType === 3) return node.textContent.replace(/\s+/g, ' ');
    if (node.nodeType !== 1 || excluded.has(node.tagName) || ['navigation', 'contentinfo'].includes(node.getAttribute('role')) || node.isContentEditable || node.getAttribute('contenteditable') === 'true' || !visible(node)) return '';
    if (node.tagName === 'BR') return '\n';
    const text = Array.from(node.childNodes, read).join('');
    return blocks.has(node.tagName) ? `\n${text}\n` : text;
  }

  function clean(text) {
    return text.split('\n').map(line => line.trim().replace(/[ \t]+/g, ' ')).filter(Boolean).join('\n');
  }

  const roots = [...document.querySelectorAll('main, article, [role="main"]'), document.body].filter(Boolean);
  let root = document.body, text = '';
  for (const candidate of roots) {
    const captured = clean(read(candidate));
    if (captured) { root = candidate; text = captured; break; }
  }
  const heading = root && [...root.querySelectorAll('h1')].find(visible);
  return { title: heading ? clean(read(heading)) : document.title, text, sourceUrl: location.href };
})();
