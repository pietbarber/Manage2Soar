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

    // Issue #567: Dynamically set navbar-spacer height to match actual navbar height
    // This ensures content offset stays correct even if navbar height changes
    // (e.g., text wrapping, zoom level, font size changes)
    function updateNavbarSpacerHeight() {
        const spacer = document.querySelector('.navbar-spacer');
        if (spacer) {
            const navbarHeight = navbar.offsetHeight;
            spacer.style.height = navbarHeight + 'px';
        }
    }

    // Set initial spacer height
    updateNavbarSpacerHeight();

    // Update on window resize (handles zoom, viewport changes)
    let resizeTicking = false;
    window.addEventListener('resize', function () {
        if (!resizeTicking) {
            resizeTicking = true;
            window.requestAnimationFrame(function () {
                updateNavbarSpacerHeight();
                resizeTicking = false;
            });
        }
    }, { passive: true });

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

        // Exact match, or path segment match for non-root links
        // Ensures '/member' doesn't match when on '/members/123'
        const isActive =
            currentPath === href ||
            (href !== '/' && currentPath.startsWith(href + '/'));

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
    if (offcanvasEl && typeof bootstrap !== 'undefined' && bootstrap.Offcanvas) {
        offcanvasEl.querySelectorAll('.nav-link:not(.dropdown-toggle), .dropdown-item').forEach(function (link) {
            link.addEventListener('click', function (event) {
                // Respect default-prevented events (e.g., custom handlers)
                if (event.defaultPrevented) {
                    return;
                }

                // Only auto-close on primary (left) button clicks
                if (event.button !== 0) {
                    return;
                }

                // Do not interfere with modified clicks (open in new tab/window)
                if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
                    return;
                }

                // Do not auto-close for explicit new-tab targets
                const targetAttr = link.getAttribute('target');
                if (targetAttr && targetAttr.toLowerCase() === '_blank') {
                    return;
                }

                // Check if mobile viewport at click time
                if (window.innerWidth < 992) {
                    const offcanvas = bootstrap.Offcanvas.getInstance(offcanvasEl);
                    if (offcanvas) {
                        // Let the browser handle navigation; just hide immediately
                        offcanvas.hide();
                    }
                }
            });
        });
    }
});
