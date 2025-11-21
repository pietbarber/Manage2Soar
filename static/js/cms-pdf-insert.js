/**
 * CMS PDF Insert Functionality
 * Shared functionality for inserting PDF iframes in TinyMCE editors
 */

// Deprecated - use validateAndSanitizeUrl instead
function validatePdfUrl(url) {
    // DEPRECATED: Use validateAndSanitizeUrl for new code.
    // This function now returns the same object as validateAndSanitizeUrl.
    console.warn('validatePdfUrl is deprecated. Use validateAndSanitizeUrl instead.');
    return validateAndSanitizeUrl(url);
}

function validateAndSanitizeUrl(url) {
    try {
        // Prevent javascript: and data: URLs (critical security fix)
        if (url.toLowerCase().startsWith('javascript:') ||
            url.toLowerCase().startsWith('data:') ||
            url.toLowerCase().startsWith('vbscript:')) {
            return {
                isValid: false,
                error: 'JavaScript, data, and VBScript URLs are not allowed for security reasons'
            };
        }

        // Create URL object to validate and sanitize
        let urlObj;
        try {
            // Handle relative URLs by adding https if no protocol specified
            if (!url.match(/^https?:\/\//i)) {
                url = 'https://' + url;
            }
            urlObj = new URL(url);
        } catch (e) {
            return {
                isValid: false,
                error: 'Invalid URL format'
            };
        }

        // Only allow HTTP and HTTPS protocols
        if (!['http:', 'https:'].includes(urlObj.protocol)) {
            return {
                isValid: false,
                error: 'Only HTTP and HTTPS URLs are allowed'
            };
        }

        // Check if URL appears to be a PDF
        const pathname = urlObj.pathname.toLowerCase();
        const isPdf = pathname.endsWith('.pdf') ||
            urlObj.searchParams.has('pdf') ||
            pathname.includes('/pdf/');

        return {
            isValid: true,
            isPdf: isPdf,
            sanitizedUrl: urlObj.toString()
        };

    } catch (error) {
        return {
            isValid: false,
            error: 'URL validation failed: ' + error.message
        };
    }
}

function initializePdfInsert() {
    // Add a simple button next to TinyMCE toolbar
    const editorContainer = document.querySelector('.tox-tinymce');
    if (editorContainer && !document.querySelector('.pdf-insert-btn')) {
        const pdfButton = document.createElement('button');
        pdfButton.type = 'button';
        pdfButton.className = 'btn btn-outline-primary btn-sm pdf-insert-btn';
        pdfButton.innerHTML = '📄 Insert PDF';
        pdfButton.style.marginLeft = '10px';

        pdfButton.onclick = function () {
            const url = prompt('Enter PDF URL:');

            if (!url || !url.trim()) {
                return; // User cancelled or entered empty URL
            }

            const cleanedUrl = url.trim();

            // Comprehensive URL validation and sanitization (SECURITY FIX)
            const validationResult = validateAndSanitizeUrl(cleanedUrl);

            if (!validationResult.isValid) {
                alert(`Invalid URL: ${validationResult.error}\n\nPlease enter a valid HTTPS URL ending with .pdf`);
                return;
            }

            // Additional confirmation for non-PDF URLs
            if (!validationResult.isPdf) {
                const confirmEmbed = confirm(
                    `Warning: This URL does not appear to be a PDF file.\n\nURL: ${validationResult.sanitizedUrl}\n\nDo you want to embed it anyway?`
                );

                if (!confirmEmbed) {
                    return;
                }
            }

            // HTML-escape the URL to prevent injection (SECURITY FIX)
            const escapedUrl = validationResult.sanitizedUrl
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;');

            // Create secure iframe with sandbox attribute (SECURITY FIX)
            const iframe = `<div class="pdf-container">
    <iframe
        src="${escapedUrl}"
        width="100%"
        height="600px"
        style="border: 1px solid #ddd; border-radius: 8px;"
        loading="lazy"
        sandbox="allow-popups allow-forms"
        referrerpolicy="no-referrer"
        title="PDF Document">
        <p>Your browser does not support iframes. <a href="${escapedUrl}" target="_blank" rel="noopener noreferrer">Click here to view the PDF</a></p>
    </iframe>
    <p><small><a href="${escapedUrl}" target="_blank" rel="noopener noreferrer">Open PDF in new tab</a></small></p>
</div><p>&nbsp;</p>`;

            // Insert using insertContent instead of setContent (IMPROVEMENT)
            const editor = tinymce.activeEditor;
            if (editor) {
                editor.insertContent(iframe);
                console.log('PDF embedded successfully with security validation:', validationResult.sanitizedUrl);
            } else {
                alert('Editor not found. Please try again.');
            }
        };

        // Insert button after TinyMCE loads
        const toolbar = editorContainer.querySelector('.tox-toolbar__primary');
        if (toolbar) {
            toolbar.appendChild(pdfButton);
        }
    }
}

// Initialize PDF insert when TinyMCE is ready
function initializeTinyMCEPdfInsert() {
    // Use a single retry mechanism with exponential backoff
    let attempts = 0;
    const maxAttempts = 5;

    function tryInitialize() {
        const editorContainer = document.querySelector('.tox-tinymce');
        if (editorContainer && !document.querySelector('.pdf-insert-btn')) {
            initializePdfInsert();
        } else if (attempts < maxAttempts) {
            attempts++;
            setTimeout(tryInitialize, Math.pow(2, attempts) * 100); // Exponential backoff
        }
    }

    tryInitialize();
}
