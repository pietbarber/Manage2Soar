/**
 * TinyMCE YouTube Embed Fix for Issue #277
 *
 * Extends TinyMCE configuration to add media_url_resolver and video_template_callback
 * for proper YouTube embedding with referrer policy.
 *
 * This file must be loaded AFTER django-tinymce's initialization script.
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

    // Store the original tinymce.init if it exists
    if (typeof tinymce !== 'undefined' && tinymce.init) {
        const originalInit = tinymce.init.bind(tinymce);

        // Override tinymce.init to inject our callbacks
        tinymce.init = function (config) {
            // Add our media_url_resolver callback
            config.media_url_resolver = function (data) {
                return new Promise(function (resolve, reject) {
                    const url = data.url;

                    // Parse URL using URL API for robust hostname checking
                    let hostname = '';
                    let urlObj = null;
                    try {
                        urlObj = new URL(url);
                        hostname = urlObj.hostname.toLowerCase();
                    } catch (e) {
                        // Invalid URL, reject to let TinyMCE's default resolver try
                        reject();
                        return;
                    }

                    // Check if this is a YouTube URL using proper hostname matching
                    if (
                        hostname === 'youtube.com' ||
                        hostname === 'www.youtube.com' ||
                        hostname === 'youtu.be'
                    ) {
                        let videoId = null;

                        // Extract video ID from watch URL using URLSearchParams
                        if (
                            (hostname === 'youtube.com' || hostname === 'www.youtube.com') &&
                            url.indexOf('/watch') !== -1
                        ) {
                            const vParam = urlObj.searchParams.get('v');
                            if (vParam && /^[a-zA-Z0-9_-]+$/.test(vParam)) {
                                videoId = vParam;
                            }
                        }
                        // Extract video ID from short URL
                        else if (hostname === 'youtu.be') {
                            const match = urlObj.pathname.match(/^\/([a-zA-Z0-9_-]+)/);
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

                    // Let TinyMCE handle other URLs by rejecting the promise
                    reject();
                });
            };

            // Add our video_template_callback with HTML escaping
            config.video_template_callback = function (data) {
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
            };

            // Call the original init with our modified config
            return originalInit(config);
        };
    }
})();
