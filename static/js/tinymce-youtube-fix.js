/**
 * TinyMCE YouTube Embed Fix for Issue #277 and #422
 * PDF Embedding for Issue #273, #341
 *
 * Extends TinyMCE configuration to add media_url_resolver and video_template_callback
 * for proper YouTube embedding with referrer policy.
 * Also adds PDF insertion button that bypasses TinyMCE content filtering.
 *
 * IMPORTANT: TinyMCE 6.x uses CALLBACK-STYLE API, not Promise-style!
 * Signature: (data, resolve, reject) => { resolve({ html: '...' }); }
 *
 * This script must be loaded AFTER the TinyMCE library but BEFORE DOMContentLoaded
 * fires (when django-tinymce's init_tinymce.js calls tinyMCE.init).
 */

(function () {
    'use strict';

    // Sandbox policy for PDF embeds (Issue #1069).
    // Chrome's built-in PDF viewer refuses to activate inside ANY sandboxed
    // iframe, regardless of which tokens are granted, so PDFs are rendered by
    // our own self-hosted pdf.js viewer (static/pdfjs-viewer/) instead. That
    // viewer is same-origin, trusted code, so the surrounding iframe can stay
    // genuinely sandboxed for every embed — there is no longer a
    // trusted/untrusted sandbox distinction.
    var PDF_VIEWER_SANDBOX = 'allow-scripts allow-same-origin allow-downloads allow-modals';
    var DEFAULT_PDF_VIEWER_URL = '/static/pdfjs-viewer/viewer.html';

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
     * Validate URL for PDF embedding (security check)
     * Only allows HTTP/HTTPS URLs to prevent XSS via javascript: or data: URIs
     */
    function parsePdfUrl(url) {
        if (!url || typeof url !== 'string') return false;
        try {
            return new URL(url.trim(), window.location.origin);
        } catch (e) {
            return null;
        }
    }

    function isValidPdfUrl(url) {
        var parsedUrl = parsePdfUrl(url);
        return parsedUrl !== null &&
            (parsedUrl.protocol === 'http:' || parsedUrl.protocol === 'https:');
    }

    function isTrustedPdfUrl(url, trustedUrlPrefixes) {
        try {
            var parsedUrl = parsePdfUrl(url);
            if (!parsedUrl || !isValidPdfUrl(url)) return false;
            var hasTrustedPrefix = trustedUrlPrefixes.some(function (prefix) {
                try {
                    var parsedPrefix = new URL(prefix, window.location.origin);
                    var prefixPath = parsedPrefix.pathname;
                    var isPrefixPath = parsedUrl.pathname === prefixPath ||
                        parsedUrl.pathname.indexOf(
                            prefixPath.endsWith('/') ? prefixPath : prefixPath + '/'
                        ) === 0;
                    return parsedPrefix.origin === parsedUrl.origin &&
                        isPrefixPath;
                } catch (e) {
                    return false;
                }
            });
            return hasTrustedPrefix;
        } catch (e) {
            return false;
        }
    }

    /**
     * Classify a candidate PDF URL so callers know whether it's safe to embed:
     * - 'trusted': matches TINYMCE_PDF_TRUSTED_URL_PREFIXES (e.g. our own
     *   /cms/document-pdf/ endpoint).
     * - 'cross-origin': a different origin than this site; safe to hand to
     *   the pdf.js viewer (it fetches independently of our session/cookies).
     * - 'same-origin-blocked': on our own origin but NOT the trusted PDF
     *   endpoint — never embedded, since the viewer's same-origin fetch would
     *   otherwise run with the visitor's full session privileges.
     * - 'invalid': not a usable http(s) URL at all.
     */
    function classifyPdfUrl(url, trustedUrlPrefixes) {
        var parsedUrl = parsePdfUrl(url);
        if (!parsedUrl || !isValidPdfUrl(url)) return 'invalid';
        if (isTrustedPdfUrl(url, trustedUrlPrefixes)) return 'trusted';
        return parsedUrl.origin === window.location.origin ? 'same-origin-blocked' : 'cross-origin';
    }

    function buildViewerSrc(viewerUrl, targetUrl) {
        return viewerUrl + '?file=' + encodeURIComponent(targetUrl);
    }

    /**
     * If `src` already points at our pdf.js viewer, return the wrapped
     * `file` target URL; otherwise null. Used to make re-normalization
     * idempotent instead of wrapping an already-wrapped viewer URL again.
     */
    function extractViewerTarget(src, viewerUrl) {
        try {
            var parsed = new URL(src, window.location.origin);
            var viewerParsed = new URL(viewerUrl, window.location.origin);
            if (parsed.origin !== viewerParsed.origin || parsed.pathname !== viewerParsed.pathname) {
                return null;
            }
            return parsed.searchParams.get('file');
        } catch (e) {
            return null;
        }
    }

    /**
     * Generate PDF embed HTML. The iframe always points at the self-hosted
     * pdf.js viewer (Issue #1069) with a fixed, genuine sandbox — the viewer
     * itself fetches and renders `url`, so Chrome's native PDF
     * viewer/sandbox incompatibility never comes into play.
     */
    function generatePdfEmbedHtml(url, viewerUrl) {
        var escapedUrl = escapeHtml(url);
        var viewerSrc = escapeHtml(buildViewerSrc(viewerUrl, url));
        return '<div class="pdf-container">' +
            '<iframe src="' + viewerSrc + '" ' +
            'sandbox="' + PDF_VIEWER_SANDBOX + '" ' +
            'width="100%" height="600" ' +
            'frameborder="0" ' +
            'loading="lazy" ' +
            'title="Embedded PDF document">' +
            '</iframe>' +
            '<p><small><a href="' + escapedUrl + '" target="_blank" rel="noopener noreferrer">' +
            'Open PDF in new tab</a></small></p>' +
            '</div>';
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

        // Add setup callback to inject YouTube notice and PDF button
        var originalSetup = config.setup;
        config.setup = function (editor) {
            // Call original setup if it exists
            if (typeof originalSetup === 'function') {
                originalSetup(editor);
            }

            var trustedPdfUrlPrefixes = config.pdf_trusted_url_prefixes || [];
            var pdfViewerUrl = config.pdf_viewer_url || DEFAULT_PDF_VIEWER_URL;
            editor.on('GetContent', function (event) {
                var container = document.createElement('div');
                container.innerHTML = event.content || '';
                var iframes = container.querySelectorAll('.pdf-container iframe');
                for (var index = 0; index < iframes.length; index++) {
                    var iframe = iframes[index];
                    var src = iframe.getAttribute('src');
                    if (!src) continue;

                    var targetUrl = extractViewerTarget(src, pdfViewerUrl) || src;
                    var classification = classifyPdfUrl(targetUrl, trustedPdfUrlPrefixes);
                    if (classification === 'invalid' || classification === 'same-origin-blocked') {
                        // Never embed an untrusted same-origin URL, wrapped or not.
                        iframe.removeAttribute('src');
                        iframe.setAttribute('sandbox', '');
                        continue;
                    }
                    iframe.setAttribute('src', buildViewerSrc(pdfViewerUrl, targetUrl));
                    iframe.setAttribute('sandbox', PDF_VIEWER_SANDBOX);
                }
                event.content = container.innerHTML;
            });

            // Register PDF insert button (Issue #273, #341)
            editor.ui.registry.addButton('insertpdf', {
                text: '📄 Insert PDF',
                tooltip: 'Insert an embedded PDF document',
                onAction: function () {
                    var url = prompt(
                        'Enter the PDF URL (must be https:// or http://):\n\n' +
                        'Tip: for files already uploaded to this site, use the document\'s ' +
                        '/cms/document-pdf/ link, not the raw storage URL.'
                    );
                    if (!url) return;
                    url = url.trim();
                    if (!isValidPdfUrl(url)) {
                        alert('Invalid URL. Please enter a valid http:// or https:// URL.');
                        return;
                    }
                    var classification = classifyPdfUrl(url, trustedPdfUrlPrefixes);
                    if (classification === 'same-origin-blocked') {
                        alert(
                            'This URL is on this site but is not the trusted PDF link.\n\n' +
                            'Please use the document\'s /cms/document-pdf/ link instead, or upload the file here.'
                        );
                        return;
                    }
                    // Check if URL ends with .pdf and warn if not
                    if (classification !== 'trusted' && !url.toLowerCase().endsWith('.pdf')) {
                        var proceed = confirm(
                            'This URL does not end with .pdf\n\n' +
                            'If this is not a PDF file, it may not display correctly.\n\n' +
                            'Continue anyway?'
                        );
                        if (!proceed) return;
                    }
                    var html = generatePdfEmbedHtml(url, pdfViewerUrl);
                    editor.insertContent(html, { format: 'raw' });
                }
            });

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
