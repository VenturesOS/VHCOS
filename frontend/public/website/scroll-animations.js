// ========================================
// Scroll Animations & Micro-interactions
// Uses Intersection Observer for performance
// ========================================

(function() {
  'use strict';

  // ===== SCROLL REVEAL =====
  // Auto-detect and animate sections, cards, grids, images
  function initScrollReveal() {
    // Selectors for elements that should animate on scroll
    var revealSelectors = [
      // Sections with inline styles (most content on these pages)
      'section',
      // Grid containers
      '[style*="display:grid"]',
      '[style*="display: grid"]',
      // Cards with rounded corners
      '[style*="border-radius:16px"]',
      '[style*="border-radius: 16px"]',
      '[style*="border-left: 4px"]',
      '[style*="border-left:4px"]',
      // Images with rounded corners
      '[style*="border-radius"] > img',
      'img[style*="border-radius"]',
      // Manually tagged elements
      '.reveal',
      '.reveal-left',
      '.reveal-right',
      '.reveal-scale'
    ];

    // Get all grid children (cards) for stagger animation
    var gridContainers = document.querySelectorAll('[style*="display:grid"], [style*="display: grid"]');
    
    gridContainers.forEach(function(grid) {
      // Skip footer grids and very small grids
      if (grid.closest('footer') || grid.closest('[style*="background:#111827"]')) return;
      
      grid.classList.add('stagger-children');
      var children = grid.children;
      for (var i = 0; i < children.length; i++) {
        if (!children[i].classList.contains('reveal') && 
            !children[i].classList.contains('reveal-left') &&
            !children[i].classList.contains('reveal-right')) {
          children[i].classList.add('reveal');
        }
      }
    });

    // Tag standalone sections that aren't inside grids
    var sections = document.querySelectorAll('section');
    sections.forEach(function(section) {
      // Skip hero sections (they have their own entrance animation)
      if (section.querySelector('[style*="font-size:56px"]') ||
          section.querySelector('[style*="font-size:52px"]') ||
          section.querySelector('[style*="font-size:48px"]')) return;
      
      // Add reveal to direct block children that aren't already tagged
      var blockChildren = section.querySelectorAll(':scope > div, :scope > h2, :scope > p');
      blockChildren.forEach(function(child) {
        if (!child.classList.contains('reveal') && !child.closest('.stagger-children')) {
          child.classList.add('reveal');
        }
      });
    });

    // Collect all reveal elements
    var revealElements = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale');

    if (!revealElements.length) return;

    // Use Intersection Observer for performance
    if ('IntersectionObserver' in window) {
      var observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('visible');
            // Stop observing once visible (one-time animation)
            observer.unobserve(entry.target);
          }
        });
      }, {
        threshold: 0.15,
        rootMargin: '0px 0px -60px 0px'
      });

      revealElements.forEach(function(el) {
        observer.observe(el);
      });
    } else {
      // Fallback: just show everything
      revealElements.forEach(function(el) {
        el.classList.add('visible');
      });
    }
  }

  // ===== BACK TO TOP BUTTON =====
  function initBackToTop() {
    var btn = document.createElement('button');
    btn.className = 'back-to-top';
    btn.setAttribute('aria-label', 'Back to top');
    btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 15l-6-6-6 6"/></svg>';
    document.body.appendChild(btn);

    btn.addEventListener('click', function() {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });

    // Show/hide based on scroll position
    var ticking = false;
    window.addEventListener('scroll', function() {
      if (!ticking) {
        requestAnimationFrame(function() {
          if (window.scrollY > 400) {
            btn.classList.add('show');
          } else {
            btn.classList.remove('show');
          }
          ticking = false;
        });
        ticking = true;
      }
    });
  }

  // ===== PARALLAX HERO (subtle) =====
  function initHeroParallax() {
    var hero = document.querySelector('[style*="background-image"]');
    if (!hero) return;

    var ticking = false;
    window.addEventListener('scroll', function() {
      if (!ticking) {
        requestAnimationFrame(function() {
          var scrolled = window.scrollY;
          if (scrolled < hero.offsetHeight) {
            hero.style.backgroundPositionY = (scrolled * 0.3) + 'px';
          }
          ticking = false;
        });
        ticking = true;
      }
    });
  }

  // ===== COUNTER ANIMATION (for stat numbers) =====
  function initCounterAnimation() {
    var statElements = document.querySelectorAll('[style*="font-size:48px"][style*="font-weight:800"], [style*="font-size: 48px"]');
    if (!statElements.length) return;

    var observer = new IntersectionObserver(function(entries) {
      entries.forEach(function(entry) {
        if (entry.isIntersecting) {
          var el = entry.target;
          var text = el.textContent.trim();
          // Check if it's a number (with optional + or % suffix)
          var match = text.match(/^(\d+)([+%]?)$/);
          if (match) {
            var target = parseInt(match[1]);
            var suffix = match[2] || '';
            animateCounter(el, 0, target, suffix, 1200);
          }
          observer.unobserve(el);
        }
      });
    }, { threshold: 0.5 });

    statElements.forEach(function(el) { observer.observe(el); });
  }

  function animateCounter(el, start, end, suffix, duration) {
    var startTime = null;
    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      // Ease out cubic
      var eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = Math.floor(eased * (end - start) + start) + suffix;
      if (progress < 1) {
        requestAnimationFrame(step);
      }
    }
    requestAnimationFrame(step);
  }

  // ===== INIT ALL =====
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      initScrollReveal();
      initBackToTop();
      initHeroParallax();
      initCounterAnimation();
    });
  } else {
    initScrollReveal();
    initBackToTop();
    initHeroParallax();
    initCounterAnimation();
  }

  // Respect reduced motion preference
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.documentElement.style.setProperty('--animation-duration', '0s');
    var reveals = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale');
    reveals.forEach(function(el) {
      el.style.transition = 'none';
      el.classList.add('visible');
    });
  }
})();
