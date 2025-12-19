# Issue #422: TinyMCE YouTube Videos Stopped Inserting

## Issue
**GitHub Issue**: #422  
**Problem**: After changes in #322 or #326, YouTube videos stopped inserting when using the TinyMCE media dialog. The dialog would appear, the user could enter a YouTube URL, but after clicking OK, nothing would be inserted into the HTML.

## Root Cause

The `media_url_resolver` callback in `static/js/tinymce-youtube-fix.js` had a fundamental API signature mismatch with TinyMCE 6.x.

### The API Signature Mismatch

**Our old code (WRONG)**:
```javascript
// Function that RETURNS a Promise
media_url_resolver = function(data) {
    return new Promise(function(resolve, reject) {
        // ... YouTube URL handling ...

        // For non-YouTube or invalid URLs:
        reject();  // ❌ WRONG: This breaks TinyMCE's internal handling
    });
};
```

**What TinyMCE 6.x actually expects**:
```javascript
// Function that ACCEPTS resolve/reject as callback parameters
media_url_resolver = function(data, resolve, reject) {
    // ... YouTube URL handling ...

    // For non-YouTube or invalid URLs:
    resolve({ html: '' });  // ✅ CORRECT: Falls back to default behavior
};
```

### Why This Matters

The critical difference is in the function signature itself:

- **Old approach**: `function(data) { return new Promise(...) }` — a function that **returns** a Promise
- **TinyMCE 6.x requirement**: `function(data, resolve, reject) { ... }` — a function that **accepts** resolve/reject as parameters

Per [TinyMCE 6 media plugin documentation](https://www.tiny.cloud/docs/tinymce/6/media/):

> The `media_url_resolver` option takes a callback-style handler: `(data, resolve, reject) => void`
>
> "If you would like to **fall back to the default media embed logic**, call `resolve({ html: '' })`"

**Why our code broke**:  
TinyMCE 6.x calls the handler with THREE arguments: `resolver(data, resolveCallback, rejectCallback)`. Our function only accepted ONE argument (`data`) and returned a Promise. TinyMCE doesn't wait for returned Promises—it only uses the callback parameters. This meant our resolver was called but TinyMCE never received a response, causing ALL media insertion (including YouTube embeds) to fail silently.

## Solution Implemented

**File**: `static/js/tinymce-youtube-fix.js`

Changed the function signature from Promise-returning to callback-accepting:

```javascript
// NEW CODE - CORRECT (Callback-style for TinyMCE 6.x)
function youtubeMediaUrlResolver(data, resolve, reject) {
    var url = data.url;

    // Parse URL and extract video ID
    // ...

    if (videoId) {
        // YouTube URL with valid video ID - provide embed HTML
        var embedHtml = '<iframe src="https://www.youtube.com/embed/' + videoId + '" ...></iframe>';
        resolve({ html: embedHtml });
        return;
    }

    // For non-YouTube URLs or invalid video IDs, fall back to TinyMCE default
    resolve({ html: '' });  // ✅ CORRECT: Callback-style fallback
}
```

### What Changed

1. **Function signature**: `function(data)` → `function(data, resolve, reject)`
2. **Return behavior**: Removed `return new Promise(...)` — now directly calls `resolve()` or `reject()`
3. **Fallback handling**: Changed from `reject()` to `resolve({ html: '' })` for non-YouTube URLs

This ensures TinyMCE receives responses via the callback parameters it provides, restoring media insertion functionality.

## E2E Tests Updated

Updated tests in `e2e_tests/e2e/test_tinymce.py`:

1. **Removed `xfail` marker** from `test_youtube_url_inserts_embed` — test now passes
2. **Renamed test**: `test_non_youtube_url_rejected` → `test_non_youtube_url_falls_back_to_default`
3. **Updated test assertions**: Now expect `resolve({ html: '' })` instead of rejection for non-YouTube URLs
4. **Added edge case tests**:
   - `test_youtube_url_with_missing_video_id` — URLs like `https://www.youtube.com/watch` (no `v` parameter)
   - `test_youtube_url_with_invalid_video_id` — URLs with invalid characters in video ID
   - `test_youtube_short_url_with_missing_video_id` — Short URLs like `https://youtu.be/` (no video ID in path)

All tests verify that the callback-style API is correctly implemented and that fallback behavior works as expected.

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
- `test_youtube_url_inserts_embed` — Verifies YouTube videos can be inserted
- `test_non_youtube_url_falls_back_to_default` — Verifies non-YouTube URLs fall back to TinyMCE default
- Edge case tests for invalid/missing video IDs

## Files Modified

- `static/js/tinymce-youtube-fix.js` — Changed `media_url_resolver` from Promise-returning to callback-accepting signature
- `e2e_tests/e2e/test_tinymce.py` — Updated tests for callback-style API and added edge case coverage
- `cms/utils.py` — Enhanced YouTube iframe fix to validate all required permissions in `allow` attribute
- `cms/tests/test_utils.py` — Added 16 comprehensive unit tests for `fix_youtube_embeds` utility
- `members/templates/members/member_view.html` — Applied `fix_youtube_embeds` filter to member biographies

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
✅ **RESOLVED** — Issue #422 fixed by updating `media_url_resolver` to use TinyMCE 6.x callback-style API instead of Promise-returning function
