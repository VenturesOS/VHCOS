/**
 * Internal Linking Engine — SEO Content Silo
 *
 * Auto-links pillar keywords in HTML content.
 * Rules:
 *   - Max 5 links per page
 *   - No duplicate anchor text
 *   - No linking inside headings, existing links, buttons
 *   - No self-linking (current slug excluded)
 *   - Controlled anchor variation per pillar
 */

const PILLAR_LINK_MAP = {
  '/industrial-recruitment': [
    'industrial recruitment services',
    'industrial recruitment',
    'manufacturing hiring solutions',
    'industrial talent acquisition',
    'factory hiring',
  ],
  '/hr-consulting-services': [
    'hr consulting services',
    'hr consulting',
    'human resources consulting',
    'workforce consulting',
    'hr advisory',
  ],
  '/career-insights': [
    'career insights',
    'career guidance',
    'professional development guidance',
    'career intelligence',
    'career advice',
  ],
};

const MAX_LINKS = 5;
const SKIP_TAGS = new Set(['H1', 'H2', 'H3', 'H4', 'A', 'BUTTON', 'SUMMARY', 'CODE', 'PRE']);

/**
 * Inject internal links into sanitized HTML content.
 * @param {string} html - DOMPurify-sanitized HTML string
 * @param {string} currentSlug - Current page slug (excluded from linking)
 * @returns {string} HTML with internal links injected
 */
export function injectInternalLinks(html, currentSlug) {
  if (!html || typeof window === 'undefined') return html;

  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div>${html}</div>`, 'text/html');
  const root = doc.body.firstChild;

  // Build keyword list excluding current page
  const currentPath = `/${currentSlug}`;
  const keywords = [];
  for (const [path, anchors] of Object.entries(PILLAR_LINK_MAP)) {
    if (path === currentPath) continue;
    for (const anchor of anchors) {
      keywords.push({ text: anchor, href: path, lower: anchor.toLowerCase() });
    }
  }

  // Sort longest-first so "industrial recruitment services" matches before "industrial recruitment"
  keywords.sort((a, b) => b.lower.length - a.lower.length);

  let linkCount = 0;
  const usedAnchors = new Set();
  const usedHrefs = new Set();

  // Walk all text nodes inside safe parent elements
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      // Skip if inside a heading, link, button, etc.
      let parent = node.parentElement;
      while (parent && parent !== root) {
        if (SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
        parent = parent.parentElement;
      }
      // Only link inside content elements
      const directParent = node.parentElement;
      if (!directParent) return NodeFilter.FILTER_REJECT;
      const tag = directParent.tagName;
      if (['P', 'LI', 'TD', 'SPAN', 'EM', 'STRONG', 'BLOCKQUOTE'].includes(tag)) {
        return NodeFilter.FILTER_ACCEPT;
      }
      return NodeFilter.FILTER_SKIP;
    }
  });

  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);

  // Skip first paragraph to avoid over-linking the intro
  let firstParagraphSkipped = false;

  for (const textNode of textNodes) {
    if (linkCount >= MAX_LINKS) break;

    // Skip first <p> content
    const parentP = textNode.parentElement?.closest('p');
    if (parentP && !firstParagraphSkipped) {
      // Check if this is inside the very first <p> in the root
      const allPs = root.querySelectorAll('p');
      if (allPs.length > 0 && allPs[0] === parentP) {
        firstParagraphSkipped = true;
        continue;
      }
    }

    const text = textNode.textContent;

    for (const kw of keywords) {
      if (linkCount >= MAX_LINKS) break;
      if (usedAnchors.has(kw.lower)) continue;

      // Max 2 links per target URL (for anchor variation, not spam)
      const hrefCount = [...usedHrefs].filter(h => h === kw.href).length;
      if (hrefCount >= 2) continue;

      const idx = text.toLowerCase().indexOf(kw.lower);
      if (idx === -1) continue;

      // Found a match — split the text node and insert an anchor
      const before = text.substring(0, idx);
      const match = text.substring(idx, idx + kw.text.length);
      const after = text.substring(idx + kw.text.length);

      const beforeNode = doc.createTextNode(before);
      const anchor = doc.createElement('a');
      anchor.href = kw.href;
      anchor.textContent = match;
      anchor.setAttribute('data-internal-link', 'true');
      const afterNode = doc.createTextNode(after);

      const parent = textNode.parentNode;
      parent.insertBefore(beforeNode, textNode);
      parent.insertBefore(anchor, textNode);
      parent.insertBefore(afterNode, textNode);
      parent.removeChild(textNode);

      linkCount++;
      usedAnchors.add(kw.lower);
      usedHrefs.add(kw.href);
      break; // Move to next text node after one replacement per node
    }
  }

  return root.innerHTML;
}
