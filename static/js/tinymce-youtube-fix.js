/**
 * TinyMCE YouTube Embed Fix for Issue #277 and #422
 *
 * Extends TinyMCE configuration to add media_url_resolver and video_template_callback
 * for proper YouTube embedding with referrer policy.
 *
 * IMPORTANT: TinyMCE 6.x uses CALLBACK-STYLE API, not Promise-style!
 * Signature: (data, resolve, reject) => { resolve({ html: '...' }); }
 *
 * This script must be loaded AFTER the TinyMCE library but BEFORE DOMContentLoaded
 * fires (when django-tinymce's init_tinymce.js calls tinyMCE.init).
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

    /**
     * TinyMCE 6.x media_url_resolver callback
     * Signature: (data, resolve, reject) => void
     * - data.url: the URL entered by the user
     * - resolve({ html: '...' }): call with HTML to embed, or empty string for default
     * - reject({ msg: '...' }): call to show error message
     */
    function youtubeMediaUrlResolver(data, resolve, reject) {
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
                // Use YouTube's official iframe attributes from their oEmbed API
                var embedHtml = '<iframe src="https://www.youtube.com/embed/' + escapeHtml(videoId) +
                    '" width="560" height="315" frameborder="0" ' +
                    'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" ' +
                    'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>';
                resolve({ html: embedHtml });
                return;
            }
        }

        // Let TinyMCE handle other URLs with default embed logic
        // Per TinyMCE docs: resolve with empty html to fall back to default
        resolve({ html: '' });
    }

    /**
     * TinyMCE video_template_callback with HTML escaping
     * Signature: (data) => string
     * Returns the HTML for video elements
     */
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

    /**
     * TinyMCE iframe_template_callback with referrer policy for Error 153 fix
     * Signature: (data) => string
     * Returns the HTML for iframe elements (including YouTube embeds)
     */
    function iframeTemplateCallback(data) {
        return '<iframe src="' + escapeHtml(data.source) +
            '" width="' + escapeHtml(data.width || 560) +
            '" height="' + escapeHtml(data.height || 315) +
            '" frameborder="0" ' +
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" ' +
            'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>';
    }

    // Wrapper function to inject our callbacks into any TinyMCE config
    function injectCallbacks(config) {
        // Add our media_url_resolver callback for YouTube embedding
        config.media_url_resolver = youtubeMediaUrlResolver;

        // Add our video_template_callback with HTML escaping
        config.video_template_callback = videoTemplateCallback;

        // Add iframe_template_callback with referrer policy for Error 153 fix
        config.iframe_template_callback = iframeTemplateCallback;

        // Add setup callback to inject YouTube notice into media dialog
        var originalSetup = config.setup;
        config.setup = function (editor) {
            // Call original setup if it exists
            if (typeof originalSetup === 'function') {
                originalSetup(editor);
            }

            // Add notice to media dialog when it opens
            editor.on('OpenWindow', function (e) {
                var dialog = e.dialog;
                if (dialog && dialog.getData) {
                    var data = dialog.getData();
                    // Check if this is the media dialog (has source field)
                    if (data && typeof data.source !== 'undefined') {
                        // Wait for dialog to render, then add notice
                        setTimeout(function () {
                            addYouTubeNoticeToDialog();
                        }, 100);
                    }
                }
            });
        };

        return config;
    }

    /**
     * Add a notice to the media dialog explaining Error 153 in preview
     */
    function addYouTubeNoticeToDialog() {
        // Find the dialog body
        var dialogBody = document.querySelector('.tox-dialog__body-content');
        if (!dialogBody) return;

        // Check if notice already exists
        if (document.getElementById('youtube-preview-notice')) return;

        // Create notice element
        var notice = document.createElement('div');
        notice.id = 'youtube-preview-notice';
        notice.style.cssText = 'background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 4px; padding: 8px 12px; margin-bottom: 12px; font-size: 13px; color: #856404;';
        notice.innerHTML = '<strong>📺 YouTube Note:</strong> The video preview may show "Error 153" in the editor, but it will display correctly after you save the page.';

        // Insert at the top of the dialog body
        dialogBody.insertBefore(notice, dialogBody.firstChild);
    }

    // Override TinyMCE init - handles both tinymce.init and tinyMCE.init
    function setupOverride() {
        // Check both possible global names (they're usually the same object)
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
