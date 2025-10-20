// Shared Tablesort initializer for Manage2Soar
// - Defines a reusable 'last-name' parser that reads data-sort-value or text
// - Initializes any table with class 'sort'
// - Dispatches a 'tablesort:ready' event when initialization completes
(function () {
    if (typeof window === 'undefined') return;
    function initTablesort() {
        if (typeof Tablesort === 'undefined') return false;

        // Custom parser to sort by data-sort-value (last name) falling back to text
        try {
            Tablesort.extend('last-name',
                function () { return true; },
                function (a, b) { return a.localeCompare(b); },
                function (td) {
                    return td.getAttribute && td.getAttribute('data-sort-value') ? td.getAttribute('data-sort-value') : td.textContent.trim();
                }
            );
        } catch (e) {
            // ignore if already defined
        }

        document.querySelectorAll('table.sort').forEach(function (table) {
            try {
                new Tablesort(table);
            } catch (e) {
                // swallow per-table errors to avoid breaking other pages
                console.error('Tablesort init error:', e);
            }
        });

        // Notify pages that Tablesort is ready so page-specific behaviors can run
        try {
            document.dispatchEvent(new Event('tablesort:ready'));
        } catch (e) {
            // ignore
        }
    }

    // If Tablesort isn't immediately available (loader may still be fetching),
    // poll for a short time before giving up.
    function tryInit(retriesLeft) {
        var ok = initTablesort();
        if (ok) return;
        if (retriesLeft <= 0) {
            console.warn('Tablesort not available after retries; table sorting disabled.');
            return;
        }
        setTimeout(function () { tryInit(retriesLeft - 1); }, 100);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { tryInit(30); });
    } else {
        // Already loaded; give it some time for loader to inject script
        setTimeout(function () { tryInit(30); }, 0);
    }
})();
