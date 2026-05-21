// Mobile Menu Toggle & Overlay
document.addEventListener('DOMContentLoaded', function() {
  var mobileToggle = document.querySelector('.mobile-menu-toggle');
  var nav = document.querySelector('.nav');

  // Create overlay element
  var overlay = document.createElement('div');
  overlay.className = 'mobile-overlay';
  document.body.appendChild(overlay);

  function openMenu() {
    nav.classList.add('active');
    overlay.classList.add('active');
    mobileToggle.textContent = '\u2715';
    document.body.style.overflow = 'hidden';
  }

  function closeMenu() {
    nav.classList.remove('active');
    overlay.classList.remove('active');
    mobileToggle.textContent = '\u2630';
    document.body.style.overflow = '';
  }

  if (mobileToggle) {
    mobileToggle.addEventListener('click', function() {
      if (nav.classList.contains('active')) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    // Close menu when clicking overlay
    overlay.addEventListener('click', closeMenu);

    // Close menu when clicking nav links (not dropdown)
    var navLinks = nav.querySelectorAll('a');
    navLinks.forEach(function(link) {
      link.addEventListener('click', function() {
        if (!link.closest('.dropdown-menu') && !link.closest('.login-dropdown')) {
          closeMenu();
        }
      });
    });
  }

  // Close menu on window resize (if going to desktop)
  window.addEventListener('resize', function() {
    if (window.innerWidth > 768 && nav && nav.classList.contains('active')) {
      closeMenu();
    }
  });
});

// Smooth Scroll
document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
  anchor.addEventListener('click', function (e) {
    e.preventDefault();
    var target = document.querySelector(this.getAttribute('href'));
    if (target) {
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }
  });
});

// Login Dropdown (shared across pages)
function toggleLoginDropdown() {
  var dropdown = document.getElementById('loginDropdown');
  if (dropdown) {
    dropdown.classList.toggle('show');
  }
}

// Close dropdown when clicking outside
document.addEventListener('click', function(e) {
  if (!e.target.closest('.login-dropdown')) {
    var dropdown = document.getElementById('loginDropdown');
    if (dropdown) {
      dropdown.classList.remove('show');
    }
  }
});
