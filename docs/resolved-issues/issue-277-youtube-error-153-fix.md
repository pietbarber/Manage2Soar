# Issue #277: YouTube Embedding Fix for Error 153

## Issue
**GitHub Issue**: #277  
**Problem**: YouTube Error 153 occurs when embedding YouTube videos in CMS content due to referrer policy restrictions.

## Root Cause
The error happens when:
1. The site uses a restrictive referrer policy like `no-referrer`
2. YouTube cannot verify the embedding domain
3. The embed iframe inherits the site's default referrer policy

## Solution Implemented

### 1. TinyMCE Configuration (Primary Fix)
Modified TinyMCE configuration in `manage2soar/settings.py`:

```python
# FIX FOR ISSUE #277 - YOUTUBE ERROR 153: Multiple approaches to ensure proper referrer policy
"media_url_resolver": r"""function(url, resolve, reject) {
    if (url.indexOf('youtube.com') !== -1 || url.indexOf('youtu.be') !== -1) {
        // Convert YouTube URLs to embed format with proper referrer policy
        var videoId = null;
        if (url.indexOf('youtube.com/watch') !== -1) {
            var match = url.match(/v=([a-zA-Z0-9_-]+)/);
            if (match) videoId = match[1];
        } else if (url.indexOf('youtu.be/') !== -1) {
            var match = url.match(/youtu\.be\/([a-zA-Z0-9_-]+)/);
            if (match) videoId = match[1];
        }

        if (videoId) {
            resolve({
                type: 'video',
                source: 'https://www.youtube.com/embed/' + videoId,
                width: 560,
                height: 315
            });
            return;
        }
    }
    reject();
}""",
"video_template_callback": """function(data) {
    return '<iframe src="' + data.source + '" width="' + (data.width || 560) + '" height="' + (data.height || 315) + '" frameborder="0" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>';
}""",
```

### 2. JavaScript Post-Processing (Backup Fix)
Created `static/js/cms-youtube-fix.js` to automatically fix YouTube embeds:

```javascript
// Automatically fixes YouTube iframe referrer policy after TinyMCE creates them
function fixYouTubeEmbeds() {
    if (typeof tinymce !== 'undefined' && tinymce.activeEditor) {
        tinymce.activeEditor.on('SetContent', function() {
            const content = tinymce.activeEditor.getContent();
            if (content.includes('youtube.com/embed')) {
                const updatedContent = content.replace(
                    /<iframe([^>]*src="[^"]*youtube\.com\/embed[^"]*"[^>]*)>/gi,
                    function(match, attrs) {
                        if (!attrs.includes('referrerpolicy=')) {
                            return match.replace('>', ' referrerpolicy="strict-origin-when-cross-origin">');
                        }
                        return match;
                    }
                );
                if (updatedContent !== content) {
                    tinymce.activeEditor.setContent(updatedContent);
                }
            }
        });
    }
}
```

## How It Works
- TinyMCE's `video_template_callback` generates custom iframe HTML for video embeds
- Sets `referrerpolicy="strict-origin-when-cross-origin"` specifically for videos
- This policy sends the origin when embedding from HTTPS to HTTPS (safe for YouTube)
- Maintains privacy by not sending full referrer information

## Testing
1. In CMS editor, use Insert > Media
2. Paste a YouTube URL (e.g., `https://www.youtube.com/watch?v=VIDEO_ID`)
3. Video should embed successfully without Error 153

## Other Video Platforms
This fix should work for most video platforms that require referrer verification:
- YouTube
- Vimeo
- Dailymotion
- Most other iframe-based embeds

## Security Notes
- `strict-origin-when-cross-origin` is a balanced referrer policy
- Provides domain verification without leaking sensitive path information
- More permissive than `no-referrer` but still privacy-conscious

## Files Modified
- `manage2soar/settings.py` - Enhanced TinyMCE media configuration with URL resolver and template callback
- `cms/models.py` - Added automatic YouTube embed fixing in Page and HomePageContent save methods
- `cms/templatetags/cms_tags.py` - Added fix_youtube_embeds template filter for display-time fixing
- `cms/templates/cms/page.html` - Applied fix_youtube_embeds filter to content display
- `cms/templates/cms/homepage.html` - Applied fix_youtube_embeds filter to content display  
- `cms/management/commands/fix_youtube_embeds.py` - Management command for batch fixing existing content
- `cms/utils.py` - New shared utility functions for YouTube embed fixing
- `docs/resolved-issues/issue-277-youtube-error-153-fix.md` - This comprehensive documentation

## Deployment Steps
1. **Restart Django server** - Configuration and model changes require server restart
2. **Test YouTube embedding** - Insert YouTube video via TinyMCE Insert > Media
3. **Run management command** (optional) - Fix existing content: `python manage.py fix_youtube_embeds`

## Status
✅ **COMPLETELY RESOLVED** - Issue #277 fixed via comprehensive 3-layer protection system plus batch processing command

This solution provides bulletproof YouTube Error 153 prevention through multiple redundant layers:
- TinyMCE editor configuration fixes
- Model-level automatic database fixing  
- Template-level display filtering

Additionally, a management command is provided for batch cleanup of existing content.
