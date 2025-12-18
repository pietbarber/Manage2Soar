# Issue #422: TinyMCE YouTube Videos Stopped Inserting

## Issue
**GitHub Issue**: #422  
**Problem**: After changes in #322 or #326, YouTube videos stopped inserting when using the TinyMCE media dialog. The dialog would appear, the user could enter a YouTube URL, but after clicking OK, nothing would be inserted into the HTML.

## Root Cause

The issue was in `static/js/tinymce-youtube-fix.js`. The `media_url_resolver` callback was using `reject()` for non-YouTube URLs, which is contrary to TinyMCE's documented behavior.

### Problem Code

```javascript
// OLD CODE - INCORRECT
media_url_resolver = function(data) {
    return new Promise(function(resolve, reject) {
        // ... YouTube URL handling ...

        // For non-YouTube or invalid URLs:
        reject();  // ❌ WRONG: This breaks TinyMCE's promise handling
    });
};
```

### TinyMCE Documentation States

Per [TinyMCE media plugin documentation](https://www.tiny.cloud/docs/tinymce/latest/media/):

> "If, in your handler, you would like to **fall back to the default media embed logic**, call the `resolve` callback with an object where the `html` property is set to an **empty string**, like this: `resolve({ html: '' })`."

The `reject()` call was breaking TinyMCE's internal promise chain, preventing ANY media from being inserted—including the properly resolved YouTube embed HTML.

## Solution Implemented

Changed all `reject()` calls to `resolve({ html: '' })`:

**File**: `static/js/tinymce-youtube-fix.js`

```javascript
// NEW CODE - CORRECT
media_url_resolver = function(data) {
    return new Promise(function(resolve, reject) {
        // ... YouTube URL handling returns resolve({ html: '<iframe...>' })

        // For non-YouTube or invalid URLs:
        resolve({ html: '' });  // ✅ CORRECT: Falls back to TinyMCE default
    });
};
```

### Changes Made

1. **Invalid URL handling**: Changed from `reject()` to `resolve({ html: '' })`
2. **Non-YouTube URL handling**: Changed from `reject()` to `resolve({ html: '' })`

## E2E Tests Updated

Updated tests in `e2e_tests/e2e/test_tinymce.py`:

1. **Removed `xfail` marker** from `test_youtube_url_inserts_embed`
2. **Renamed** `test_non_youtube_url_rejected` to `test_non_youtube_url_falls_back_to_default`
3. **Updated assertions** to expect `resolve({ html: '' })` instead of rejection for non-YouTube URLs

## Testing

### Verify YouTube Embedding Works

1. Navigate to a CMS edit page (e.g., `/cms/create/page/`)
2. Click Insert > Media (or the media button in toolbar)
3. Paste a YouTube URL: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
4. Click Save/OK
5. **Expected**: An iframe with the YouTube embed appears in the editor
6. Save the page and verify the video plays on the rendered page

### Verify E2E Tests Pass

```bash
pytest e2e_tests/e2e/test_tinymce.py -v
```

All tests should pass, including:
- `test_youtube_url_inserts_embed` - Now passes without xfail marker
- `test_non_youtube_url_falls_back_to_default` - Verifies fallback behavior

## Files Modified

- `static/js/tinymce-youtube-fix.js` - Fixed Promise handling for media_url_resolver
- `e2e_tests/e2e/test_tinymce.py` - Updated tests for new behavior

## Deployment Steps

1. Deploy code changes
2. Run `python manage.py collectstatic --noinput` to update JavaScript
3. Clear browser cache to ensure new JS is loaded
4. No database migrations required

## Related Issues

- **Issue #277**: Original YouTube Error 153 fix that introduced `media_url_resolver`
- **Issue #322**: Table overflow fix that may have exposed this issue
- **Issue #397**: Console errors fix that refactored the TinyMCE callbacks

## Status
✅ **RESOLVED** - Issue #422 fixed by using correct TinyMCE Promise resolution pattern
