# Issue #397: TinyMCE JavaScript Console Errors

## Issue
**GitHub Issue**: #397  
**Problem**: TinyMCE generates JavaScript console errors/warnings on pages with rich text editors. Three warnings appear (once per TinyMCE widget instance):
- "Invalid value passed for the `table_responsive_width` option"
- "Invalid value passed for the `media_url_resolver` option"
- "Invalid value passed for the `video_template_callback` option"

## Root Cause

The issue occurred due to incompatibility between how `django-tinymce` serializes Python configuration and how TinyMCE expects JavaScript callbacks:

### 1. **Deprecated Option** (`table_responsive_width`)
- `table_responsive_width: True` was added in Issue #322 to fix table overflow
- This option is **not documented** in current TinyMCE (v6+) documentation
- The correct modern equivalent is `table_sizing_mode: 'responsive'`

### 2. **Invalid Function Format** (`media_url_resolver` and `video_template_callback`)
- These callbacks were added in Issue #277 to fix YouTube Error 153
- They were defined as Python raw strings (r"""function(...){}""") in `settings.py`
- `django-tinymce` serializes the config dict to JSON, which passes these as **strings**, not **functions**
- TinyMCE expects actual JavaScript functions, not string representations

### 3. **Why Strings Don't Work**
```python
# In settings.py - this becomes a STRING in JavaScript
"media_url_resolver": r"""function(url, resolve, reject) { ... }"""

# TinyMCE expects an actual function object
media_url_resolver: function(data) { return new Promise(...); }
```

## Solution Implemented

### 1. Removed Deprecated/Invalid Options from `settings.py`

**File**: `manage2soar/settings.py`

**Changes**:
- ✅ **Removed** `table_responsive_width: True` (deprecated)
- ✅ **Kept** `table_sizing_mode: "responsive"` (correct modern option)
- ✅ **Removed** string-based `media_url_resolver` callback
- ✅ **Removed** string-based `video_template_callback` callback

**Result**: Settings.py now only contains options that can be properly serialized to JSON.

### 2. Created JavaScript Override File

**File**: `static/js/tinymce-youtube-fix.js`

This file:
1. **Intercepts** `tinymce.init()` calls
2. **Injects** proper JavaScript function callbacks for YouTube embedding
3. **Preserves** the original functionality from Issue #277

**How It Works**:
```javascript
// Override tinymce.init to add our callbacks
tinymce.init = function(config) {
    // Add JavaScript function (not string!)
    config.media_url_resolver = function(data) {
        return new Promise(function(resolve, reject) {
            // YouTube URL detection and embed logic
        });
    };

    config.video_template_callback = function(data) {
        // Video iframe generation with referrerpolicy
    };

    // Call original init with modified config
    return originalInit(config);
};
```

### 3. Updated All TinyMCE Templates

Added script tag after `{{ form.media }}` in all forms using TinyMCE:

**Updated Templates**:
- `templates/cms/edit_page.html`
- `templates/cms/create_page.html`
- `templates/cms/edit_homepage.html`
- `members/templates/members/biography.html`
- `cms/templates/cms/feedback_form.html`
- `instructors/templates/instructors/log_ground_instruction.html`
- `logsheet/templates/logsheet/edit_closeout_form.html`

**Pattern**:
```django
{{ form.media }}
{# Issue #397: TinyMCE YouTube fix must load after form.media #}
<script src="{% static 'js/tinymce-youtube-fix.js' %}"></script>
```

**Why After `form.media`**:
- `form.media` loads django-tinymce's JavaScript
- Our override must execute **after** TinyMCE is loaded but **before** it's initialized
- The override intercepts the initialization call to inject our callbacks

## Testing

### Verify Console Errors Are Gone

1. Open Edit Closeout page (or any CMS edit page)
2. Open browser DevTools Console (F12)
3. Look for TinyMCE warnings - should be **none**

### Verify YouTube Embedding Still Works (Issue #277)

1. In CMS editor, click Insert > Media
2. Paste a YouTube URL: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
3. Video should embed successfully
4. Inspect the iframe HTML:
   ```html
   <iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"
           width="560" height="315"
           frameborder="0"
           allowfullscreen
           referrerpolicy="strict-origin-when-cross-origin">
   </iframe>
   ```
5. Video should play without Error 153

### Verify Tables Are Still Responsive (Issue #322)

1. Insert a table in TinyMCE editor
2. Table should respect container width (no overflow scrolling)
3. Table should have `table-layout: fixed` applied
4. Long text in cells should wrap, not expand table width

## Technical Details

### TinyMCE Configuration Layers

1. **`settings.py`**: Base configuration (JSON-serializable only)
   - Options with primitive values (strings, numbers, booleans, objects)
   - Cannot contain JavaScript functions

2. **JavaScript Override**: Runtime callbacks (actual functions)
   - `media_url_resolver` - Custom URL resolver for video embeds
   - `video_template_callback` - Custom HTML template for video elements
   - `audio_template_callback` - Could be added if needed

### Why Not Use Widget Customization?

Alternative approaches that were **not** used:

1. **Custom TinyMCE Widget Class**:
   ```python
   class CustomTinyMCE(TinyMCE):
       def render(self, name, value, attrs=None, renderer=None):
           # Add custom JavaScript here
   ```
   - ❌ More complex
   - ❌ Would need to update all form definitions
   - ❌ Harder to maintain

2. **Django-TinyMCE JS() Wrapper**:
   ```python
   from tinymce import JS
   config = {
       "media_url_resolver": JS("function(data) { ... }")
   }
   ```
   - ❌ `django-tinymce` doesn't support `JS()` wrapper
   - ❌ Would require patching django-tinymce

3. **Inline `<script>` in Templates**:
   ```html
   <script>
   tinymce.init({ ... callbacks ... });
   </script>
   ```
   - ❌ Code duplication across templates
   - ❌ No automatic integration with django-tinymce
   - ❌ Must manually replicate all settings

**Why JavaScript Override is Best**:
- ✅ Clean separation: Settings in Python, callbacks in JavaScript
- ✅ Single source of truth for callback logic
- ✅ Minimal template changes (one line each)
- ✅ Preserves django-tinymce automatic widget rendering
- ✅ Easy to maintain and extend

## Files Modified

### Removed Invalid Config
- `manage2soar/settings.py` - Removed string-based callbacks and deprecated option

### Added JavaScript Override
- `static/js/tinymce-youtube-fix.js` - New file with callback functions

### Updated Templates
- `templates/cms/edit_page.html`
- `templates/cms/create_page.html`
- `templates/cms/edit_homepage.html`
- `members/templates/members/biography.html`
- `cms/templates/cms/feedback_form.html`
- `instructors/templates/instructors/log_ground_instruction.html`
- `logsheet/templates/logsheet/edit_closeout_form.html`

## Compatibility Notes

### TinyMCE Version
- Current version: `django-tinymce==4.1.0`
- TinyMCE core version: 6.x (bundled with django-tinymce)
- This fix is compatible with TinyMCE 6.0+ API

### Deprecated Options Reference
- `table_responsive_width` → use `table_sizing_mode: 'responsive'`
- Callback strings → use JavaScript function objects

### Migration from TinyMCE 5 to 6
From TinyMCE migration guide:
- Media plugin callbacks signature changed to use Promises
- Table sizing options were modernized
- Some options that were strings in v5 must be functions in v6

## Lessons Learned

1. **JSON Serialization Limits**: Python config dicts are serialized to JSON, which cannot represent JavaScript functions. Functions must be injected at runtime.

2. **Documentation Lag**: Features added to fix specific issues (like `table_responsive_width`) may become deprecated in newer versions. Always check current docs.

3. **Deprecation Warnings Are Helpful**: Console warnings alerted us to invalid options that would have been silent failures otherwise.

4. **Load Order Matters**: Override script must load after TinyMCE but before initialization.

5. **Test Across Browser Consoles**: Console warnings are the first sign of configuration issues.

## Prevention Guidelines

### When Adding TinyMCE Features

1. **Check Current Documentation**:
   - https://www.tiny.cloud/docs/tinymce/latest/
   - Verify option is documented for current version

2. **Use Correct Option Types**:
   - Primitive values (string, number, boolean) → `settings.py`
   - JavaScript callbacks/functions → JavaScript override file

3. **Test in Browser Console**: Look for warnings/errors after changes

4. **Document Version Compatibility**: Note TinyMCE version when adding features

### When Upgrading TinyMCE

1. **Review Migration Guides**: Check TinyMCE version-specific migration docs
2. **Check Deprecated Options**: Review settings.py against current docs
3. **Test Console**: Look for new warnings after upgrade
4. **Update Documentation**: Note changes in resolved-issues docs

## Related Issues

- **Issue #277**: YouTube Error 153 fix (original source of callbacks)
- **Issue #322**: Table overflow fix (original source of `table_responsive_width`)
- **Issue #375 Redux**: Edit Closeout form (one of the pages showing errors)

## References

- [TinyMCE 6 Migration Guide](https://www.tiny.cloud/docs/tinymce/6/migration-from-5x/)
- [TinyMCE Media Plugin Documentation](https://www.tiny.cloud/docs/tinymce/latest/media/)
- [TinyMCE Table Options Documentation](https://www.tiny.cloud/docs/tinymce/latest/table-options/)
- [django-tinymce Documentation](https://django-tinymce.readthedocs.io/)
