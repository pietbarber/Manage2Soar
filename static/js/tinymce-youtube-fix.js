/**
 * TinyMCE YouTube Embed Fix for Issue #277 and #422
 *
 * Extends TinyMCE configuration to add media_url_resolver and video_template_callback
 * for proper YouTube embedding with referrer policy.
 *
 * This script must be loaded AFTER the TinyMCE library but BEFORE DOMContentLoaded
 * fires (when django-tinymce's init_tinymce.js calls tinyMCE.init).
 *
 * Critical: django-tinymce calls tinyMCE.init() (uppercase MCE), so we override that.
 * The tinymce and tinyMCE globals are typically the same object in TinyMCE 5+.
 */

(function () {
    'use strict';

    // Utility function to HTML-escape attribute values (XSS prevention)
    function escapeHtml(str) {
        if (str === undefined || str === null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // The media_url_resolver function for YouTube URLs
    function youtubeMediaUrlResolver(data) {
        return new Promise(function (resolve) {
            var url = data.url;

            // Parse URL using URL API for robust hostname checking
            var hostname = '';
            var urlObj = null;
            try {
                urlObj = new URL(url);
                hostname = urlObj.hostname.toLowerCase();
            } catch (e) {
                // Invalid URL, let TinyMCE's default resolver handle it
                resolve({ html: '' });
                return;
            }

            // Check if this is a YouTube URL using proper hostname matching
            if (
                hostname === 'youtube.com' ||
                hostname === 'www.youtube.com' ||
                hostname === 'youtu.be'
            ) {
                var videoId = null;

                // Extract video ID from watch URL using URLSearchParams
                if (
                    (hostname === 'youtube.com' || hostname === 'www.youtube.com') &&
                    url.indexOf('/watch') !== -1
                ) {
                    var vParam = urlObj.searchParams.get('v');
                    if (vParam && /^[a-zA-Z0-9_-]+$/.test(vParam)) {
                        videoId = vParam;
                    }
                }
                // Extract video ID from short URL
                else if (hostname === 'youtu.be') {
                    var match = urlObj.pathname.match(/^\/([a-zA-Z0-9_-]+)/);
                    if (match && /^[a-zA-Z0-9_-]+$/.test(match[1])) {
                        videoId = match[1];
                    }
                }

                if (videoId) {
                    // Video ID is validated by regex, escape for defense-in-depth
                    resolve({
                        html: '<iframe src="https://www.youtube.com/embed/' + escapeHtml(videoId) +
                            '" width="560" height="315" frameborder="0" allowfullscreen ' +
                            'referrerpolicy="strict-origin-when-cross-origin"></iframe>'
                    });
                    return;
                }
            }

            // Let TinyMCE handle other URLs with default embed logic
            // Per TinyMCE docs: resolve with empty html to fall back to default
            resolve({ html: '' });
        });
    }

    // The video_template_callback function with HTML escaping
    function videoTemplateCallback(data) {
        return '<video width="' + escapeHtml(data.width || 560) +
            '" height="' + escapeHtml(data.height || 315) + '"' +
            (data.poster ? ' poster="' + escapeHtml(data.poster) + '"' : '') +
            ' controls="controls">\n' +
            '<source src="' + escapeHtml(data.source) + '"' +
            (data.sourcemime ? ' type="' + escapeHtml(data.sourcemime) + '"' : '') + ' />\n' +
            (data.altsource
                ? '<source src="' + escapeHtml(data.altsource) + '"' +
                (data.altsourcemime ? ' type="' + escapeHtml(data.altsourcemime) + '"' : '') + ' />\n'
                : '') +
            '</video>';
    }

    // Wrapper function to inject our callbacks into any TinyMCE config
    function injectCallbacks(config) {
        // Add our media_url_resolver callback for YouTube embedding
        config.media_url_resolver = youtubeMediaUrlResolver;

        // Add our video_template_callback with HTML escaping
        config.video_template_callback = videoTemplateCallback;

        return config;
    }

    // Override TinyMCE init - handles both tinymce.init and tinyMCE.init
    function setupOverride() {
        // Check both possible global names
        var mceGlobal = (typeof tinyMCE !== 'undefined') ? tinyMCE :
                        (typeof tinymce !== 'undefined') ? tinymce : null;

        if (!mceGlobal || !mceGlobal.init || window._tinymceYoutubeFixApplied) {
            return false;
        }

        // Store original init
        var originalInit = mceGlobal.init.bind(mceGlobal);

        // Create our wrapped init function
        var wrappedInit = function (config) {
            // Inject our callbacks into the config
            injectCallbacks(config);
            // Call original init
            return originalInit(config);
        };

        // Apply override to the global object
        mceGlobal.init = wrappedInit;

        // Both tinymce and tinyMCE should point to the same object,
        // but just in case they don't, apply to both
        if (typeof tinymce !== 'undefined' && tinymce !== mceGlobal) {
            tinymce.init = wrappedInit;
        }
        if (typeof tinyMCE !== 'undefined' && tinyMCE !== mceGlobal) {
            tinyMCE.init = wrappedInit;
        }

        // Mark as applied
        window._tinymceYoutubeFixApplied = true;
        return true;
    }

    // Apply override immediately if TinyMCE is already loaded
    if (!setupOverride()) {
        // If TinyMCE not yet loaded, try again on a microtask
        // This handles async script loading scenarios
        Promise.resolve().then(setupOverride);
    }
})();
