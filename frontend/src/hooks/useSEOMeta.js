import { useEffect, useRef } from 'react';

/**
 * Directly injects/updates meta tags + JSON-LD in <head>.
 * Handles React StrictMode double-mount correctly.
 * @param {{ title, description, canonical, ogTitle, ogDescription, ogUrl, ogType, jsonLd }} meta
 */
export function useSEOMeta(meta) {
  const elRef = useRef([]);

  useEffect(() => {
    if (!meta) return;

    // Clean up previous elements from this hook instance
    elRef.current.forEach(el => el.remove());
    elRef.current = [];

    if (meta.title) document.title = meta.title;

    const tags = [
      { attr: 'name', key: 'description', content: meta.description },
      { attr: 'property', key: 'og:title', content: meta.ogTitle || meta.title },
      { attr: 'property', key: 'og:description', content: meta.ogDescription || meta.description },
      { attr: 'property', key: 'og:url', content: meta.ogUrl },
      { attr: 'property', key: 'og:type', content: meta.ogType || 'article' },
    ];

    for (const t of tags) {
      if (!t.content) continue;
      let el = document.querySelector(`meta[${t.attr}="${t.key}"]`);
      if (!el) {
        el = document.createElement('meta');
        el.setAttribute(t.attr, t.key);
        document.head.appendChild(el);
        elRef.current.push(el);
      }
      el.setAttribute('content', t.content);
    }

    // Canonical link
    if (meta.canonical) {
      let canonical = document.querySelector('link[rel="canonical"]');
      if (!canonical) {
        canonical = document.createElement('link');
        canonical.setAttribute('rel', 'canonical');
        document.head.appendChild(canonical);
        elRef.current.push(canonical);
      }
      canonical.setAttribute('href', meta.canonical);
    }

    // JSON-LD structured data
    if (meta.jsonLd) {
      // Remove any existing managed JSON-LD
      document.querySelectorAll('script[data-seo-jsonld]').forEach(el => el.remove());
      const script = document.createElement('script');
      script.type = 'application/ld+json';
      script.setAttribute('data-seo-jsonld', 'true');
      script.textContent = JSON.stringify(meta.jsonLd);
      document.head.appendChild(script);
      elRef.current.push(script);
    }

    return () => {
      elRef.current.forEach(el => el.remove());
      elRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta?.title, meta?.description, meta?.canonical, meta?.ogTitle, meta?.ogDescription, meta?.ogUrl, meta?.ogType, JSON.stringify(meta?.jsonLd)]);
}
