// tablesort-loader.js
// Try to load a local vendored Tablesort first (static/vendor/tablesort.min.js).
// If that file isn't found, fall back to the CDN.
(function () {
    function loadScript(src, onload) {
        var s = document.createElement('script');
        s.src = src;
        s.async = false;
        s.onload = onload;
        s.onerror = function () { console.warn('Failed to load', src); };
        document.head.appendChild(s);
    }

    // Try local vendor first
    var local = '/static/vendor/tablesort.min.js';
    // Attempt to fetch the local file with a HEAD request to avoid double-executing.
    fetch(local, { method: 'HEAD' }).then(function (resp) {
        if (resp.ok) {
            loadScript(local, function () {
                // local loaded; nothing else required
            });
        } else {
            // fallback to CDN
            loadScript('https://cdn.jsdelivr.net/npm/tablesort@5.2.1/dist/tablesort.min.js');
        }
    }).catch(function () {
        // network error or file doesn't exist; fallback to CDN
        loadScript('https://cdn.jsdelivr.net/npm/tablesort@5.2.1/dist/tablesort.min.js');
    });
})();
