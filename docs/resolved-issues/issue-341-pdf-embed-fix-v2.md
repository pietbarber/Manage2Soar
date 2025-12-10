# Issue #341 Fix - PDF Embedding in CMS (Second Attempt)

## Problem
The "Insert PDF" button in the CMS TinyMCE editor was not properly embedding PDFs. Instead of creating a visible PDF iframe, it was only inserting a link:

```html
<p><a href="https://storage.googleapis.com/..." target="_blank">Open PDF in new tab</a></p>
```

## Root Cause
TinyMCE was filtering/stripping the iframe HTML during content insertion for two reasons:

1. **Missing format parameter**: `editor.insertContent(iframe)` was using default parsing which applies TinyMCE's content filters
2. **Incomplete valid_elements configuration**: The `<div class="pdf-container">` wrapper and nested structure weren't explicitly allowed in TinyMCE's `valid_children` rules

## Solution

### 1. JavaScript Fix (`static/js/cms-pdf-insert.js`)
Changed from:
```javascript
editor.insertContent(iframe);
```

To:
```javascript
editor.insertContent(iframe, { format: 'raw' });
```

The `{ format: 'raw' }` parameter tells TinyMCE to insert the HTML without applying content filters, preserving the iframe structure.

### 2. TinyMCE Configuration Fix (`manage2soar/settings.py`)
Updated `TINYMCE_DEFAULT_CONFIG`:

**Before:**
```python
"extended_valid_elements": "iframe[src|width|height|style|class|loading|sandbox|title|referrerpolicy],object[...],param[...],embed[...]",
"valid_children": "+body[iframe|object|embed]",
```

**After:**
```python
"extended_valid_elements": "iframe[src|width|height|style|class|loading|sandbox|title|referrerpolicy],div[class|style],object[...],param[...],embed[...]",
"valid_children": "+body[iframe|object|embed|div],+div[iframe|p],+p[a|small]",
```

This explicitly allows:
- `div` elements with `class` and `style` attributes (for `pdf-container`)
- Nested structure: `div > iframe` and `div > p` and `p > a` and `p > small`

## Files Modified
1. `static/js/cms-pdf-insert.js` - Added `format: 'raw'` to insertContent call
2. `manage2soar/settings.py` - Updated TinyMCE extended_valid_elements and valid_children

## Testing
After deploying these changes:
1. Open CMS page editor
2. Click "📄 Insert PDF" button
3. Enter a PDF URL (e.g., https://example.com/document.pdf)
4. Verify that a visible PDF iframe is inserted, not just a link
5. Save the page and view it - PDF should display in an iframe

## Expected Output
The inserted HTML should be:
```html
<div class="pdf-container">
    <iframe
        src="https://example.com/document.pdf"
        width="100%"
        height="600px"
        style="border: 1px solid #ddd; border-radius: 8px;"
        loading="lazy"
        sandbox="allow-scripts allow-same-origin"
        referrerpolicy="no-referrer"
        title="PDF Document">
        <p>Your browser does not support iframes. <a href="https://example.com/document.pdf" target="_blank" rel="noopener noreferrer">Click here to view the PDF</a></p>
    </iframe>
    <p><small><a href="https://example.com/document.pdf" target="_blank" rel="noopener noreferrer">Open PDF in new tab</a></small></p>
</div>
<p>&nbsp;</p>
```

## Why This Wasn't Caught Initially
The original implementation in Issue #273 likely worked during initial testing but was broken by subsequent TinyMCE configuration changes or updates that made the content filtering more strict. The `format: 'raw'` parameter is the definitive solution to prevent TinyMCE from parsing and filtering the HTML.

## Related Issues
- Issue #273: Original TinyMCE PDF embedding implementation
- Issue #322: CMS responsive CSS for tables (may have inadvertently affected TinyMCE config)
- Issue #341: This fix (second attempt after incomplete initial fix)
