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
 *   - Skip first paragraph
 */

const PILLAR_LINK_MAP = {
  '/industrial-recruitment': [
    'industrial recruitment',
    'industrial talent',
    'manufacturing hiring',
    'talent acquisition',
    'recruitment practice',
    'industrial sectors',
    'industrial and manufacturing',
    'manufacturing sectors',
  ],
  '/hr-consulting-services': [
    'hr consulting',
    'consulting and recruitment expertise',
    'consulting expertise',
    'leadership assessment',
    'psychometric profiling',
    'organisation design',
    'people strategies',
    'workforce planning',
    'compensation benchmarking',
    'workforce consulting',
    'hr advisory',
  ],
  '/career-insights': [
    'career insights',
    'career guidance',
    'career trajectories',
    'career intelligence',
    'professional development',
    'salary benchmarks',
    'salary benchmarking',
    'compensation data',
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

  // Sort longest-first so longer phrases match before substrings
  keywords.sort((a, b) => b.lower.length - a.lower.length);

  let linkCount = 0;
  const usedAnchors = new Set();
  const hrefLinkCount = {};

  // Collect text nodes in safe parent elements
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      let parent = node.parentElement;
      while (parent && parent !== root) {
        if (SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
        parent = parent.parentElement;
      }
      const tag = node.parentElement?.tagName;
      if (['P', 'LI', 'TD', 'SPAN', 'EM', 'STRONG', 'BLOCKQUOTE'].includes(tag)) {
        return NodeFilter.FILTER_ACCEPT;
      }
      return NodeFilter.FILTER_SKIP;
    }
  });

  const textNodes = [];
  while (walker.nextNode()) textNodes.push(walker.currentNode);

  // Identify first <p> to skip
  const firstP = root.querySelector('p');

  for (const textNode of textNodes) {
    if (linkCount >= MAX_LINKS) break;

    // Skip content inside the first <p>
    if (firstP && firstP.contains(textNode)) continue;

    const text = textNode.textContent;
    if (text.trim().length < 10) continue;

    for (const kw of keywords) {
      if (linkCount >= MAX_LINKS) break;
      if (usedAnchors.has(kw.lower)) continue;
      // Max 2 links to same URL
      if ((hrefLinkCount[kw.href] || 0) >= 2) continue;

      const idx = text.toLowerCase().indexOf(kw.lower);
      if (idx === -1) continue;

      // Split text node and insert anchor
      const before = text.substring(0, idx);
      const match = text.substring(idx, idx + kw.text.length);
      const after = text.substring(idx + kw.text.length);

      const frag = doc.createDocumentFragment();
      if (before) frag.appendChild(doc.createTextNode(before));
      const anchor = doc.createElement('a');
      anchor.href = kw.href;
      anchor.textContent = match;
      anchor.setAttribute('data-internal-link', 'true');
      frag.appendChild(anchor);
      if (after) frag.appendChild(doc.createTextNode(after));

      textNode.parentNode.replaceChild(frag, textNode);

      linkCount++;
      usedAnchors.add(kw.lower);
      hrefLinkCount[kw.href] = (hrefLinkCount[kw.href] || 0) + 1;
      break;
    }
  }

  return root.innerHTML;
}
