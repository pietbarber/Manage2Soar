# Issue #375 Redux: Equipment Issues Field Cleared on Maintenance Issue Submission

**Date Resolved:** December 10, 2025  
**Branch:** `issue-375-redux`  
**Related PR:** #396 (original fix), new PR TBD  
**Severity:** High - Data loss issue

## Problem Description

After successfully merging PR #396 which fixed the original Issue #375 (preserving TinyMCE content during maintenance issue submission), a new bug emerged: the `equipment_issues` textarea field was being cleared when submitting a maintenance issue via the modal.

### User Report

User typed "something something" in the equipment_issues textarea, clicked "Add Maintenance Issue", filled in the modal for aircraft 9Y, submitted the modal, and observed that the equipment_issues field was now empty.

### Symptoms

1. User enters text in equipment_issues field
2. User clicks "Add Maintenance Issue" button
3. Modal opens and user fills in maintenance issue details
4. User submits modal
5. **Page reloads** (this was the key symptom)
6. Equipment issues field is now empty
7. Maintenance issue appears in the list (so backend worked)

## Root Cause Analysis

After extensive debugging with console logging and template inspection, the root cause was identified:

**The JavaScript was not being rendered in the HTML at all.**

### Why JavaScript Wasn't Loading

The template `logsheet/templates/logsheet/edit_closeout_form.html` used:

```django
{% block extra_js %}
<script>
// AJAX code here...
</script>
{% endblock %}
```

However, the base template `templates/base.html` defines the block as:

```django
{% block extra_scripts %}{% endblock %}
```

**Block name mismatch:** `extra_js` vs `extra_scripts`

Because the block names didn't match, Django never rendered the JavaScript block, causing:

1. No AJAX functionality
2. Form submission used traditional POST with redirect
3. Page reload cleared all unsaved form data (including equipment_issues)
4. User perceived it as "field being cleared"

### Discovery Process

The issue was particularly tricky to diagnose because:

1. **Template rendering worked** - the footer text in the template updated correctly
2. **No JavaScript errors** - there was no JavaScript to run
3. **Backend worked** - the maintenance issue was successfully created
4. **AJAX "appeared" to work** - the page reload happened so fast it looked like dynamic behavior

The breakthrough came when user noted: "I'm 100% sure it's not a caching issue" and pointed out that template changes (footer text) appeared immediately, but JavaScript changes did not.

Checking the page source revealed the JavaScript block was completely absent from the rendered HTML.

## Solution

### Primary Fix: Correct Template Block Name

Changed the block name from `extra_js` to `extra_scripts`:

```django
{% block extra_scripts %}
<script>
// AJAX code here...
</script>
{% endblock %}
```

**File:** `logsheet/templates/logsheet/edit_closeout_form.html`  
**Lines:** 476-478

### Secondary Fix: DOM Insertion Method

Fixed a DOM manipulation error that appeared once JavaScript started working:

**Before:**
```javascript
const container = document.querySelector('.container');
const formContainer = document.querySelector('.closeout-form-container');
if (container && formContainer) {
    container.insertBefore(alertDiv, formContainer);
}
```

**After:**
```javascript
const container = document.querySelector('.container');
if (container) {
    container.insertBefore(alertDiv, container.firstChild);
}
```

The issue was that `insertBefore()` requires the second argument to be a **direct child** of the parent element. Using `container.firstChild` is simpler and more robust.

**Error observed:** `Failed to execute 'insertBefore' on 'Node': The node before which the new node is to be inserted is not a child of this node.`

### Additional Enhancements

Added `credentials: 'same-origin'` to the fetch request to ensure cookies are included:

```javascript
fetch(maintenanceForm.action, {
    method: 'POST',
    body: formData,
    headers: {
        'X-Requested-With': 'XMLHttpRequest',
    },
    credentials: 'same-origin'
})
```

## Testing

### Test Case 1: Preserve Equipment Issues Text

1. Navigate to closeout edit page
2. Type text in equipment_issues field (e.g., "something something")
3. Click "Add Maintenance Issue"
4. Select aircraft and enter description
5. Submit modal
6. **Expected:** equipment_issues field still contains "something something"
7. **Expected:** Success message appears at top of page
8. **Expected:** No page reload occurs
9. **Expected:** New maintenance issue appears in list

### Test Case 2: Preserve TinyMCE Content

1. Navigate to closeout edit page
2. Enter rich text in operations_summary (TinyMCE field)
3. Click "Add Maintenance Issue"
4. Select aircraft and enter description
5. Submit modal
6. **Expected:** TinyMCE content is preserved
7. **Expected:** No page reload

### Test Case 3: Error Handling

1. Navigate to closeout edit page
2. Click "Add Maintenance Issue"
3. Submit modal without selecting aircraft or entering description
4. **Expected:** Error message appears
5. **Expected:** No page reload
6. **Expected:** Modal remains open with form errors displayed

## Lessons Learned

### 1. Template Block Names Must Match Exactly

Django template inheritance requires exact block name matching. There is no error or warning if block names don't match - the block simply won't render.

**Prevention:** When adding new blocks to child templates, always verify the block name exists in the base template.

### 2. Missing JavaScript Can Masquerade as Other Issues

When JavaScript doesn't load, AJAX functionality falls back to traditional form submission, which can appear as:
- "Data being cleared"
- "Fields losing content"
- "Page refreshing unexpectedly"

**Diagnostic:** Always check browser console for JavaScript errors AND verify JavaScript is actually present in page source.

### 3. Local Dev with GCS Static Files

The project uses Google Cloud Storage (GCS) for static files even in local development. This created confusion because:
- Templates are rendered server-side (no collectstatic needed)
- Static files require collectstatic to upload to GCS
- Inline JavaScript in templates doesn't need collectstatic

**Diagnostic:** When debugging "why isn't my change showing", check if it's a template change (immediate) or static file change (needs collectstatic).

### 4. insertBefore() Parent-Child Requirement

The DOM method `insertBefore()` requires the reference node (second argument) to be a **direct child** of the parent node. This is not well documented in casual tutorials.

**Best Practice:** When inserting at the beginning of a container, use `container.firstChild` as the reference node.

### 5. Defensive Coding for AJAX

The solution includes several defensive coding practices:
- Verify elements exist before manipulating
- Add explicit `credentials: 'same-origin'` for cookie handling
- Provide fallback `alert()` if DOM manipulation fails
- Reset form only if it's actually the modal form
- Check response status before parsing JSON

## Related Issues

- **Issue #375 (Original):** TinyMCE content lost when adding maintenance issues - Fixed in PR #396
- **Issue #375 Redux:** Equipment issues textarea cleared - This issue
- **PR #396:** Original AJAX implementation (successfully merged to main)

## Files Modified

- `logsheet/templates/logsheet/edit_closeout_form.html` - Block name fix, DOM insertion fix
- `logsheet/views.py` - Removed temporary debug logging

## Deployment Notes

No database migrations required. No configuration changes required. Template changes take effect immediately upon deployment.

## Prevention

To prevent similar issues in the future:

1. **Code Review:** Check that template blocks match base template
2. **Testing:** Test JavaScript functionality in dev environment before deploying
3. **Documentation:** Document which blocks are available in base templates
4. **Linting:** Consider adding a template linter that validates block names

## Conclusion

This issue demonstrates the importance of:
- Exact template block name matching in Django
- Thorough testing of JavaScript-dependent features
- Not assuming "working in production" means "working correctly"
- Persistence in debugging when initial hypotheses don't pan out

The fix is simple (one word change: `extra_js` → `extra_scripts`), but the diagnosis required systematic elimination of false hypotheses about caching, AJAX, and form handling.
