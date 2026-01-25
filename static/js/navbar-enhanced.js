/**
 * Enhanced Navbar Functionality
 * Issue #547: Site Style Enhancements
 *
 * Features:
 * - Scroll shadow effect
 * - Active page highlighting
 * - Auto-close off-canvas on mobile nav link click
 */

document.addEventListener('DOMContentLoaded', function () {
    const navbar = document.getElementById('main-navbar');
    if (!navbar) return;

    // Add shadow when scrolled - throttled with requestAnimationFrame
    let navbarShadowTicking = false;

    function updateNavbarShadow() {
        if (window.scrollY > 10) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }
    }

    function onScroll() {
        if (!navbarShadowTicking) {
            navbarShadowTicking = true;
            window.requestAnimationFrame(function () {
                updateNavbarShadow();
                navbarShadowTicking = false;
            });
        }
    }

    window.addEventListener('scroll', onScroll, { passive: true });
    updateNavbarShadow(); // Initial check

    // Active page highlighting based on current URL
    const currentPath = window.location.pathname;
    document.querySelectorAll('.navbar-nav .nav-link, .navbar-nav .dropdown-item').forEach(function (link) {
        const href = link.getAttribute('href');
        if (!href || href === '#') return;

        // Exact match for root, or path segment match for others
        // Ensures '/member' doesn't match when on '/members/123'
        const isActive = (href === '/' && currentPath === '/') ||
            (href !== '/' && (currentPath === href || (currentPath.startsWith(href + '/') && href.endsWith('/'))));

        if (isActive) {
            link.classList.add('active');
            // Also highlight parent dropdown if this is a dropdown item
            const parentDropdown = link.closest('.dropdown');
            if (parentDropdown) {
                const toggle = parentDropdown.querySelector('.dropdown-toggle');
                if (toggle) toggle.classList.add('active');
            }
        }
    });

    // Auto-close off-canvas when a navigation link is clicked (mobile)
    const offcanvasEl = document.getElementById('navbarOffcanvas');
    if (offcanvasEl) {
        offcanvasEl.querySelectorAll('.nav-link:not(.dropdown-toggle), .dropdown-item').forEach(function (link) {
            link.addEventListener('click', function () {
                // Check if mobile viewport at click time
                if (window.innerWidth < 992) {
                    const offcanvas = bootstrap.Offcanvas.getInstance(offcanvasEl);
                    if (offcanvas) {
                        // Small delay to allow navigation to start
                        setTimeout(function () {
                            offcanvas.hide();
                        }, 150);
                    }
                }
            });
        });
    }
});
