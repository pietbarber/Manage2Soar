# Issue #600: Calendar Day Detail 500 Error - Template Syntax Error

**Issue**: [#600](https://github.com/pietbarber/Manage2Soar/issues/600)  
**PR**: [#601](https://github.com/pietbarber/Manage2Soar/pull/601)  
**Resolved**: February 3, 2026

## Summary
Users experienced 500 Internal Server Error when clicking on duty calendar dates (e.g., March 7, 2026) to view day details. The modal showed "Sorry, there was an error loading the duty information."

## Error Details

### Browser Console
```
GET https://skylinesoaring.org/duty_roster/calendar/day/2026/3/7/ 500 (Internal Server Error)
```

### Django Stack Trace
```python
django.template.exceptions.TemplateSyntaxError: Could not parse the remainder: '(not' from '(not'
```

### Affected Code
File: `duty_roster/templates/duty_roster/calendar_day_modal.html` (line 338)

**Before (invalid syntax):**
```django
{% if assignment and not assignment.is_scheduled and (not assignment.is_confirmed or assignment.tow_pilot == user or assignment.instructor == user or assignment.duty_officer == user or assignment.assistant_duty_officer == user) %}
```

## Root Cause
Django template language does not support parentheses around the `not` operator in conditional expressions. The syntax `(not assignment.is_confirmed or ...)` is **invalid**.

Django's template parser treats `(not` as a single token and cannot parse it correctly. While Python allows this syntax, Django templates use a simpler expression parser that doesn't support this pattern.

## Solution
Split the complex AND condition into nested `{% if %}` blocks to achieve the same logical behavior:

**After (valid syntax):**
```django
{% if assignment and not assignment.is_scheduled %}
  {% if not assignment.is_confirmed or assignment.tow_pilot == user or assignment.instructor == user or assignment.duty_officer == user or assignment.assistant_duty_officer == user %}
  ...
  {% endif %}
{% endif %}
```

### Logical Equivalence
Both versions implement the same logic:
- Show volunteer signup section if assignment exists AND is not scheduled AND (not confirmed OR user has a role)

The nested structure maintains the short-circuit evaluation behavior while using valid Django template syntax.

## Impact
- **Severity**: HIGH - Complete blockage of calendar day detail functionality
- **Affected Users**: All users trying to view duty day details
- **Scope**: All duty roster calendar dates, not just March 7th
- **User Experience**: Modal error message, no access to day details, ops intent, or instruction requests

## Prevention
### Django Template Best Practices
1. **Avoid parentheses with `not`**: Django templates don't support `(not condition)`
2. **Use nested `{% if %}` blocks**: For complex AND/OR logic, nest conditions
3. **Test templates after complex conditionals**: Run template validation tests
4. **Syntax validation**: Use Django's template checker during development

### Template Syntax Rules
✅ **Valid:**
```django
{% if not condition %}
{% if condition1 and condition2 %}
{% if condition1 or condition2 %}
```

❌ **Invalid:**
```django
{% if (not condition) %}  # Parentheses not supported
{% if (condition1 and condition2) or condition3 %}  # Complex grouping not supported
```

### Testing Pattern
Add E2E tests for template rendering:
```python
def test_calendar_day_detail_renders(self):
    """Test that calendar day detail modal renders without errors"""
    response = self.client.get('/duty_roster/calendar/day/2026/3/7/')
    self.assertEqual(response.status_code, 200)
    self.assertNotContains(response, "error loading")
```

## Additional Resources
- [Django Template Language Reference](https://docs.djangoproject.com/en/5.2/ref/templates/language/)
- [Django Template Syntax](https://docs.djangoproject.com/en/5.2/ref/templates/builtins/#if)
- [Template Debugging](https://docs.djangoproject.com/en/5.2/howto/custom-template-tags/#template-tag-thread-safety-considerations)

## Related Issues
None - This was an isolated template syntax error introduced in recent development.
