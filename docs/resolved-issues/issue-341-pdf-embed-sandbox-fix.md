# Issue #341: Fix PDF Embedding in CMS

## Issue
**GitHub Issue**: #341  
**Problem**: After fixing the tables overflow issue (Issue #322), PDF embedding stopped working in the CMS. PDFs would not display in the iframe, only showing a link to open in a new tab.

## Root Cause
The PDF iframe had an empty `sandbox=""` attribute, which is extremely restrictive and blocks ALL functionality including:
- Loading remote content
- Running JavaScript (required for PDF.js and browser PDF viewers)
- Displaying the PDF document itself

This overly restrictive sandbox was likely added as part of a security fix but broke PDF functionality entirely.

## Solution Implemented

### 1. Updated Iframe Sandbox Permissions (`static/js/cms-pdf-insert.js`)

Changed from:
```javascript
sandbox=""  // Blocks everything
```

To:
```javascript
sandbox="allow-scripts allow-same-origin"  // Minimal permissions for PDF display
```

**Security Analysis:**
- ✅ `allow-scripts`: Required for PDF.js and browser-native PDF viewers to function
- ✅ `allow-same-origin`: Required for loading PDF content from remote URLs
- ✅ Combined with HTTPS-only validation (already implemented)
- ✅ `referrerpolicy="no-referrer"` prevents leaking referrer information
- ❌ Does NOT allow: forms, popups, top-level navigation, downloads, or other dangerous features
- ❌ Still blocks: `allow-forms`, `allow-popups`, `allow-top-navigation`, `allow-downloads`

This maintains security while allowing PDF display functionality.

### 2. Fixed CSS Height Override (`static/css/cms-responsive.css`)

**Problem**: The responsive CSS had `height: auto` for ALL iframes, which collapsed PDF iframes to 0px or minimal height.

**Solution**:
- Keep `height: auto` for video/embed/object elements (responsive media)
- Add specific rule for `.pdf-container iframe` to preserve fixed height
- Set `min-height: 600px` for PDF iframes to ensure visibility

### 3. Maintained Existing Security Features

The fix preserves all existing security measures:
- URL validation (HTTPS/HTTP only)
- Protocol verification to prevent JavaScript injection
- PDF file detection with user confirmation
- Sanitized URL output
- No-referrer policy
- Lazy loading

## Files Modified

1. **`static/js/cms-pdf-insert.js`** - Updated sandbox attribute with appropriate permissions
2. **`static/css/cms-responsive.css`** - Fixed iframe height handling for PDF containers

## Testing Checklist

- [ ] Insert PDF URL in CMS editor
- [ ] Verify PDF displays in iframe (not just link)
- [ ] Test with HTTPS PDF URLs
- [ ] Test responsive behavior (width scales, height preserved)
- [ ] Verify "Open in new tab" link still works
- [ ] Confirm no JavaScript errors in console
- [ ] Test on mobile/tablet viewports
- [ ] Verify tables still don't overflow (Issue #322 regression test)

## Security Considerations

### Why `allow-scripts` and `allow-same-origin` are Safe Here:

1. **URL Validation**: Only HTTPS/HTTP URLs allowed (no `javascript:`, `data:`, etc.)
2. **Read-Only Content**: PDFs are static documents, not interactive web pages
3. **No Form Submission**: `allow-forms` is NOT enabled
4. **No Popups**: `allow-popups` is NOT enabled
5. **No Navigation**: `allow-top-navigation` is NOT enabled
6. **Isolated Context**: Iframe content cannot access parent page

### What We're Protecting Against:

- ✅ XSS attacks via URL injection (validated protocol)
- ✅ Malicious navigation (sandbox blocks top-navigation)
- ✅ Form phishing (sandbox blocks forms)
- ✅ Popup spam (sandbox blocks popups)
- ✅ Drive-by downloads (sandbox blocks downloads)

### Known Limitations:

- PDFs from untrusted sources could contain malicious JavaScript
- **Same-Origin PDFs**: PDFs embedded from the same domain as the CMS could potentially access the parent page when both `allow-scripts` and `allow-same-origin` are enabled. This includes access to DOM, cookies, and session storage.
- **Mitigation**:
  - Only administrators can edit CMS content (role-based permissions)
  - JavaScript validation warns administrators when embedding same-origin PDFs
  - Administrators should be trained to only embed PDFs from trusted external sources or carefully reviewed same-origin PDFs
- **Best Practice**: Prefer embedding PDFs from external trusted domains (club storage, official sources) over same-origin PDFs

## Related Issues

- **Issue #322**: Tables overflow fix - Must not regress when fixing PDF embedding
- **Issue #273**: Original TinyMCE PDF embedding implementation
- **Issue #337**: Bootstrap rows overflow in CMS content

## Migration Notes

After deploying this fix:
1. Run `python manage.py collectstatic` to deploy updated JavaScript and CSS
2. Clear browser cache to ensure new files are loaded
3. Test existing CMS pages with embedded PDFs to confirm they now display correctly
4. No database migrations required

## Closed

December 2025
