# Issue #322: TinyMCE Tables Overflow Container (CSS Table Border Discipline)

## Issue
**GitHub Issue**: #322  
**Problem**: Tables created in TinyMCE "drip to the right" and overflow their container, requiring horizontal scrolling to view content that should be contained within the page.

## Root Cause
The issue occurred due to two factors:

1. **Missing CSS wrapper**: Templates rendering TinyMCE HTML content were not wrapping it in a `<div class="cms-content">` container that enforces table containment rules.

2. **Insufficient CSS constraints**: The existing `cms-responsive.css` used `table-layout: auto` which allows tables to expand beyond their container based on content width.

## Solution Implemented

### 1. Enhanced CSS Constraints (`static/css/cms-responsive.css`)

```css
/* Force all tables to respect container width */
.cms-content table {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;  /* Override any min-width set by TinyMCE */
    table-layout: fixed !important;  /* Fixed layout respects width constraints */
    word-break: break-word;
    box-sizing: border-box;
    border-collapse: collapse;
}

/* Table cells must wrap text and respect boundaries */
.cms-content td,
.cms-content th {
    word-break: break-word;
    overflow-wrap: break-word;
    white-space: normal !important;
    max-width: 100%;
    box-sizing: border-box;
}

/* Prevent any inline styles from overriding our constraints */
.cms-content table[style],
.cms-content td[style],
.cms-content th[style] {
    max-width: 100% !important;
}
```

### 2. Added `cms-content` Wrapper to All TinyMCE Templates

**Pattern**: `<div class="cms-content">{{ content|safe }}</div>`

Templates updated:
- `cms/templates/cms/page.html` - Main CMS page (was missing wrapper)
- `instructors/templates/instructors/syllabus_grouped.html` - Header and materials
- `instructors/templates/instructors/syllabus_full.html` - Header, materials, lesson descriptions
- `instructors/templates/instructors/syllabus_detail.html` - Lesson descriptions
- `instructors/templates/instructors/_instruction_detail_fragment.html` - Instructor notes
- `members/templates/members/member_view.html` - Biography and public notes
- `members/templates/members/badges.html` - Badge descriptions
- `members/templates/members/membership_application.html` - Terms section
- `logsheet/templates/logsheet/view_closeout.html` - Safety, equipment, operations summaries
- `templates/footer.html` - Footer content
- `templates/home.html` - Homepage content
- `templates/shared/member_instruction_record.html` - Instruction reports and notes

### 3. TinyMCE Default Table Styling (`manage2soar/settings.py`)

```python
# Issue #322: Force tables to use responsive CSS by default
"table_default_styles": {
    "width": "100%",
    "max-width": "100%",
    "table-layout": "fixed",
},
"table_sizing_mode": "responsive",  # Use responsive sizing mode
"table_responsive_width": True,  # Enable responsive table widths
# Apply content CSS in the editor to match rendered output
"content_style": """
    table { width: 100% !important; max-width: 100% !important; table-layout: fixed !important; }
    td, th { word-break: break-word; white-space: normal !important; }
""",
```

## How It Works

1. **`table-layout: fixed`**: Forces the table to respect the width constraints of its container, distributing column widths equally rather than based on content.

2. **`max-width: 100% !important`**: Prevents any inline styles from expanding the table beyond its container.

3. **`word-break: break-word`**: Forces long words to break and wrap rather than expanding the cell.

4. **`cms-content` wrapper**: Provides a consistent CSS hook for all TinyMCE content, ensuring the containment rules are always applied.

5. **TinyMCE content_style**: Makes the editor preview match the rendered output, so users see accurate table behavior while editing.

## Prevention Guidelines

Added to `.github/copilot-instructions.md`:

```markdown
## TinyMCE Content Rendering (CRITICAL)
- **ALWAYS** wrap TinyMCE HTML content in a `<div class="cms-content">` container when rendering with `|safe`.
- **WHY**: Tables and other elements in TinyMCE can overflow their container without the `cms-content` CSS wrapper.
- **CSS**: `static/css/cms-responsive.css` enforces `table-layout: fixed`, `max-width: 100%`, and word-wrap constraints.
- **Pattern**: Use `<div class="cms-content">{{ content|safe }}</div>` NOT `<div>{{ content|safe }}</div>`.
```

## Testing

1. Create a CMS page with a table containing long text
2. Set table width to a percentage (e.g., 80%)
3. Save and view the rendered page
4. Table should remain within page bounds, with text wrapping appropriately

## Files Modified

- `static/css/cms-responsive.css` - Enhanced table containment CSS rules
- `manage2soar/settings.py` - TinyMCE default table styles and content CSS
- `cms/templates/cms/page.html` - Added cms-content wrapper
- `instructors/templates/instructors/syllabus_grouped.html` - Added cms-content wrappers
- `instructors/templates/instructors/syllabus_full.html` - Added cms-content wrappers
- `instructors/templates/instructors/syllabus_detail.html` - Added cms-content wrapper
- `instructors/templates/instructors/_instruction_detail_fragment.html` - Added cms-content wrapper
- `members/templates/members/member_view.html` - Added cms-content wrappers
- `members/templates/members/badges.html` - Added cms-content wrapper
- `members/templates/members/membership_application.html` - Added cms-content wrapper
- `logsheet/templates/logsheet/view_closeout.html` - Added cms-content wrappers
- `templates/footer.html` - Added cms-content wrapper
- `templates/home.html` - Added cms-content wrapper
- `templates/shared/member_instruction_record.html` - Added cms-content wrappers
- `.github/copilot-instructions.md` - Added prevention guidelines

## Deployment Steps

1. Deploy code changes
2. Run `python manage.py collectstatic --noinput` to update CSS
3. No database migrations required
4. Existing tables will automatically be constrained by the CSS rules

## Status
✅ **RESOLVED** - Issue #322 fixed with comprehensive CSS containment and documentation to prevent recurrence
