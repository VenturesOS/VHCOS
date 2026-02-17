import { useEffect } from 'react';

/**
 * Directly injects/updates meta tags in <head>.
 * More reliable than react-helmet-async for CSR in v2.
 * @param {{ title, description, canonical, ogTitle, ogDescription, ogUrl, ogType }} meta
 */
export function useSEOMeta(meta) {
  useEffect(() => {
    if (!meta) return;
    if (meta.title) document.title = meta.title;

    const tags = [
      { attr: 'name', key: 'description', content: meta.description },
      { attr: 'property', key: 'og:title', content: meta.ogTitle || meta.title },
      { attr: 'property', key: 'og:description', content: meta.ogDescription || meta.description },
      { attr: 'property', key: 'og:url', content: meta.ogUrl },
      { attr: 'property', key: 'og:type', content: meta.ogType || 'article' },
    ];

    const managed = [];
    for (const t of tags) {
      if (!t.content) continue;
      let el = document.querySelector(`meta[${t.attr}="${t.key}"]`);
      if (!el) {
        el = document.createElement('meta');
        el.setAttribute(t.attr, t.key);
        document.head.appendChild(el);
      }
      el.setAttribute('content', t.content);
      el.setAttribute('data-seo-managed', 'true');
      managed.push(el);
    }

    // Canonical link
    let canonical = document.querySelector('link[rel="canonical"]');
    if (meta.canonical) {
      if (!canonical) {
        canonical = document.createElement('link');
        canonical.setAttribute('rel', 'canonical');
        document.head.appendChild(canonical);
      }
      canonical.setAttribute('href', meta.canonical);
      canonical.setAttribute('data-seo-managed', 'true');
    }

    return () => {
      // Cleanup on unmount — remove managed tags
      document.querySelectorAll('[data-seo-managed]').forEach(el => el.remove());
    };
  }, [meta?.title, meta?.description, meta?.canonical, meta?.ogTitle, meta?.ogDescription, meta?.ogUrl, meta?.ogType]);
}
