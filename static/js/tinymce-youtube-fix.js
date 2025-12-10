/**
 * TinyMCE YouTube Embed Fix for Issue #277
 *
 * Extends TinyMCE configuration to add media_url_resolver and video_template_callback
 * for proper YouTube embedding with referrer policy.
 *
 * This file must be loaded AFTER django-tinymce's initialization script.
 */

(function() {
    'use strict';

    // Store the original tinymce.init if it exists
    if (typeof tinymce !== 'undefined' && tinymce.init) {
        const originalInit = tinymce.init.bind(tinymce);

        // Override tinymce.init to inject our callbacks
        tinymce.init = function(config) {
            // Add our media_url_resolver callback
            config.media_url_resolver = function(data) {
                return new Promise(function(resolve, reject) {
                    const url = data.url;

                    // Check if this is a YouTube URL
                    if (url.indexOf('youtube.com') !== -1 || url.indexOf('youtu.be') !== -1) {
                        let videoId = null;

                        // Extract video ID from watch URL
                        if (url.indexOf('youtube.com/watch') !== -1) {
                            const match = url.match(/v=([a-zA-Z0-9_-]+)/);
                            if (match) videoId = match[1];
                        }
                        // Extract video ID from short URL
                        else if (url.indexOf('youtu.be/') !== -1) {
                            const match = url.match(/youtu\.be\/([a-zA-Z0-9_-]+)/);
                            if (match) videoId = match[1];
                        }

                        if (videoId) {
                            resolve({
                                html: '<iframe src="https://www.youtube.com/embed/' + videoId +
                                      '" width="560" height="315" frameborder="0" allowfullscreen ' +
                                      'referrerpolicy="strict-origin-when-cross-origin"></iframe>'
                            });
                            return;
                        }
                    }

                    // Let TinyMCE handle other URLs with its default logic
                    resolve({ html: '' });
                });
            };

            // Add our video_template_callback
            config.video_template_callback = function(data) {
                return '<video width="' + (data.width || 560) + '" height="' + (data.height || 315) + '"' +
                       (data.poster ? ' poster="' + data.poster + '"' : '') +
                       ' controls="controls">\n' +
                       '<source src="' + data.source + '"' + (data.sourcemime ? ' type="' + data.sourcemime + '"' : '') + ' />\n' +
                       (data.altsource ? '<source src="' + data.altsource + '"' + (data.altsourcemime ? ' type="' + data.altsourcemime + '"' : '') + ' />\n' : '') +
                       '</video>';
            };

            // Call the original init with our modified config
            return originalInit(config);
        };
    }
})();
