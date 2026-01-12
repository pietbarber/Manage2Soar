# Issue #341: PDF Embedding in TinyMCE CMS Editor

## Issue
**GitHub Issue**: #341  
**Problem**: PDF embedding stopped working in the CMS editor. When users tried to insert PDFs, nothing appeared or the iframe was blocked by the browser.

## Root Cause

### Primary Issue: Missing JavaScript
The PDF insertion JavaScript file (`cms-pdf-insert.js`) was **deleted** at some point during code cleanup. The documentation referenced a "📄 Insert PDF" button, but the JavaScript that implemented it no longer existed in `static/js/`.

### Secondary Issue: Chrome PDF Viewer Compatibility
Previously saved PDFs had `sandbox="allow-scripts allow-same-origin"` attribute on the iframe. Chrome's built-in PDF viewer (PDFium) doesn't work with HTML5 sandboxed iframes, causing the "This page has been blocked by Chrome" message.

## Solution Implemented

### 1. Added PDF Embedding to TinyMCE YouTube Fix Script

**File**: `static/js/tinymce-youtube-fix.js`

Instead of creating a separate file, integrated PDF functionality into the existing TinyMCE extension script:

```javascript
// URL validation for security (XSS prevention)
function isValidPdfUrl(url) {
    if (!url || typeof url !== 'string') return false;
    url = url.trim();
    try {
        var urlObj = new URL(url);
        // Only allow http and https protocols
        if (urlObj.protocol !== 'http:' && urlObj.protocol !== 'https:') {
            return false;
        }
        return true;
    } catch (e) {
        return false;
    }
}

// Generate PDF embed HTML without sandbox (Chrome compatibility)
function generatePdfEmbedHtml(url) {
    var escapedUrl = escapeHtml(url);
    return '<div class="pdf-container">' +
        '<iframe src="' + escapedUrl + '" ' +
        'width="100%" height="600" ' +
        'frameborder="0" ' +
        'loading="lazy" ' +
        'title="Embedded PDF document">' +
        '</iframe>' +
        '<p><small><a href="' + escapedUrl + '" target="_blank" rel="noopener noreferrer">' +
        'Open PDF in new tab</a></small></p>' +
        '</div>';
}
```

### 2. Registered TinyMCE Button

Added button registration in the `setup` callback:

```javascript
editor.ui.registry.addButton('insertpdf', {
    text: '📄 Insert PDF',
    tooltip: 'Insert an embedded PDF document',
    onAction: function () {
        var url = prompt('Enter the PDF URL (must be https:// or http://):');
        if (url) {
            url = url.trim();
            if (isValidPdfUrl(url)) {
                // Warn if URL doesn't look like a PDF
                if (!url.toLowerCase().endsWith('.pdf')) {
                    var proceed = confirm(
                        'This URL does not end with .pdf\n\n' +
                        'If this is not a PDF file, it may not display correctly.\n\n' +
                        'Continue anyway?'
                    );
                    if (!proceed) return;
                }
                var html = generatePdfEmbedHtml(url);
                // CRITICAL: Use format:'raw' to bypass TinyMCE content filtering
                editor.insertContent(html, { format: 'raw' });
            } else {
                alert('Invalid URL. Please enter a valid http:// or https:// URL.');
            }
        }
    }
});
```

### 3. Updated TinyMCE Configuration

**File**: `manage2soar/settings.py`

Added `insertpdf` to toolbar:
```python
"toolbar": (
    "undo redo | blocks | bold italic underline | alignleft aligncenter alignright alignjustify | "
    "bullist numlist outdent indent | link image media insertpdf | table | code | fullscreen | help"
),
```

Added schema configuration to preserve iframe:
```python
# Extended valid elements to allow PDF embedding iframes
"extended_valid_elements": (
    "iframe[src|width|height|frameborder|sandbox|referrerpolicy|loading|title|allow|allowfullscreen],"
    "div[class|style]"
),
# Allow iframes inside div.pdf-container and p inside div
"valid_children": "+div[iframe|p],+body[div]",
```

Added in-editor CSS preview:
```python
"content_style": """
    table { width: 100% !important; max-width: 100% !important; table-layout: fixed !important; }
    td, th { word-break: break-word; white-space: normal !important; }
    .pdf-container { margin: 1em 0; text-align: center; border: 1px solid #ddd; border-radius: 8px; padding: 10px; background-color: #f9f9f9; }
    .pdf-container iframe { max-width: 100%; border: none; border-radius: 4px; }
""",
```

## Why No Sandbox Attribute?

### The Problem
Chrome's built-in PDF viewer (PDFium) runs in a separate process and doesn't work with HTML5 `sandbox` attribute. When `sandbox="allow-scripts allow-same-origin"` was set, Chrome would show "This page has been blocked by Chrome" instead of the PDF.

### Why It's Still Secure
1. **Browser-level sandboxing**: PDF viewers (Chrome's PDFium, Firefox's PDF.js) run in isolated OS-level processes with their own security model
2. **No parent page access**: PDFs cannot access the parent page's DOM, cookies, or JavaScript
3. **URL validation**: Only HTTP/HTTPS URLs allowed, preventing `javascript:`, `data:`, and other dangerous URI schemes
4. **HTML escaping**: All URLs are escaped via `escapeHtml()` to prevent XSS

### What HTML5 Sandbox Is For
The `sandbox` attribute is designed for untrusted third-party HTML content (ads, user-submitted iframes). Browser-native content handlers like PDF viewers have their own security model that makes HTML5 sandbox redundant and incompatible.

## Key Technical Details

### Content Filtering Bypass
TinyMCE's content filtering was stripping the iframe when using normal `insertContent()`. The fix uses:

```javascript
editor.insertContent(html, { format: 'raw' });
```

This bypasses TinyMCE's HTML sanitization and inserts the content exactly as provided.

### Existing Content Fix
For pages with PDFs that already have `sandbox` attribute saved in the database, users need to:
1. Edit the page in CMS
2. Delete the existing PDF embed
3. Re-insert using the new "📄 Insert PDF" button

Alternatively, a database migration could strip the sandbox attribute from existing content.

## Files Modified

1. **`static/js/tinymce-youtube-fix.js`**
   - Added `isValidPdfUrl()` function
   - Added `generatePdfEmbedHtml()` function
   - Added `insertpdf` button registration

2. **`manage2soar/settings.py`**
   - Added `insertpdf` to toolbar
   - Added `extended_valid_elements` for iframe preservation
   - Added `valid_children` for proper nesting
   - Added `.pdf-container` CSS to `content_style`

3. **`e2e_tests/e2e/test_tinymce.py`**
   - Added `TestTinyMCEPDFEmbed` class with 4 tests

## E2E Tests Added

```python
class TestTinyMCEPDFEmbed(DjangoPlaywrightTestCase):
    def test_insert_pdf_button_exists(self):
        """Verify the Insert PDF button is registered in the toolbar."""

    def test_insert_pdf_button_visible_in_toolbar(self):
        """Verify the Insert PDF button is visible in the toolbar."""

    def test_pdf_url_validation_rejects_javascript_urls(self):
        """Verify that javascript: URLs are rejected for PDF embedding."""

    def test_pdf_embed_html_structure(self):
        """Verify the generated PDF embed HTML has correct structure."""
```

## Testing Checklist

- [x] "📄 Insert PDF" button appears in TinyMCE toolbar
- [x] Clicking button prompts for URL
- [x] Valid HTTPS URL inserts PDF iframe
- [x] Invalid URLs (javascript:, data:) are rejected
- [x] Non-.pdf URLs show confirmation warning
- [x] PDF displays correctly in Chrome after saving
- [x] PDF displays correctly in Firefox after saving
- [x] "Open PDF in new tab" fallback link works
- [x] Responsive sizing works on mobile

## Related Issues

- **Issue #273**: Original TinyMCE PDF embedding implementation
- **Issue #322**: Tables overflow fix (may have exposed this issue)
- **Issue #422**: YouTube embedding fix (similar TinyMCE callback issues)

## Deployment Steps

1. Deploy code changes
2. Run `python manage.py collectstatic --noinput` to update JavaScript
3. Clear browser cache to ensure new JS is loaded
4. For existing pages with broken PDFs, re-insert using new button
5. No database migrations required

## Pull Request

**PR #490**: Fix PDF embedding in TinyMCE CMS editor (Issue #341)

## Status
✅ **RESOLVED** — Issue #341 fixed by adding PDF embedding functionality to tinymce-youtube-fix.js with proper URL validation, removing incompatible sandbox attribute, and adding TinyMCE configuration for iframe preservation.
