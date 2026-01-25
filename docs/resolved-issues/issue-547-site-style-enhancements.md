# Issue #547: Site Style Enhancements

**Date Implemented:** January 24, 2026
**T-Shirt Size:** XXL
**Status:** Implemented (pending PR merge)

## Overview

Comprehensive styling overhaul to modernize the site's appearance, inspired by the legacy Google Sites design. This issue addresses navbar improvements, banner images, and mobile navigation UX.

## Features Implemented

### 1. Fixed-Top Sticky Navbar
- **Location:** [templates/base.html](../../templates/base.html)
- Navbar remains fixed at the top 56px of the viewport while scrolling
- Scroll shadow effect (subtle box-shadow appears after scrolling 10px)
- Proper z-index layering (1030) for modal/dropdown compatibility
- CSS in [static/css/navbar-enhanced.css](../../static/css/navbar-enhanced.css)

### 2. Active Page Highlighting
- Current page/section highlighted with dusty rose underline (`#c9849e`)
- Works for both top-level nav links and dropdown items
- Parent dropdown toggles also highlight when child is active
- JavaScript-based URL path matching

### 3. Mobile Off-Canvas Sidebar Navigation
- **Hamburger menu** triggers slide-in sidebar from left (not dropdown collapse)
- **Width:** 85% viewport, max 320px
- **Larger touch targets:** 54px min-height nav links, 1.2rem font size
- **Dark backdrop:** 60% opacity overlay when menu is open
- **Smooth animations:** 0.3s ease-in-out for slide and backdrop fade
- **Header:** Club logo + name with close button
- **Auto-close:** Sidebar closes when nav link clicked (150ms delay)

### 4. Banner Images with Parallax Effect
- **Model field:** `Page.banner_image` (ImageField)
- **Location:** [cms/models.py](../../cms/models.py)
- **Migration:** `0015_add_banner_image_to_page.py`
- Banner displays at top of CMS pages with parallax scrolling (`background-attachment: fixed`)
- Graceful degradation: pages without banners display normally
- Admin interface: Collapsible "Banner Image" fieldset in Page admin

### 5. Auto-Contrast Text Color Detection
- JavaScript analyzes banner image brightness using canvas sampling
- Automatically applies `light-text` (white) or `dark-text` (dark gray) class
- Gradient overlay for text readability
- Located in [cms/templates/cms/includes/banner.html](../../cms/templates/cms/includes/banner.html)

### 6. Print-Friendly Navbar
- Navbar and spacer hidden in print media (`@media print`)
- Backdrop also hidden in print
- No interference with printed document layouts

## Files Changed

### New Files
| File | Purpose |
|------|---------|
| `static/css/navbar-enhanced.css` | Sticky navbar, off-canvas, active highlighting styles |
| `static/css/banner-parallax.css` | Parallax banner and auto-contrast text styles |
| `cms/templates/cms/includes/banner.html` | Banner partial template with brightness detection |
| `cms/migrations/0015_add_banner_image_to_page.py` | Add banner_image field to Page model |

### Modified Files
| File | Changes |
|------|---------|
| `templates/base.html` | Fixed-top navbar, off-canvas structure, scroll shadow JS, active highlighting JS |
| `cms/models.py` | Added `banner_image` ImageField to Page model |
| `cms/admin.py` | Added collapsible "Banner Image" fieldset |
| `cms/templates/cms/page.html` | Include banner partial, conditional title display |
| `utils/upload_entropy.py` | Added `upload_cms_banner()` function |
| `e2e_tests/e2e/test_basic_setup.py` | Updated navbar toggle test for off-canvas |
| `cms/docs/models.md` | Added banner_image to ERD and documentation |

## Technical Details

### CSS Architecture
```
static/css/
├── navbar-enhanced.css    # 300+ lines
│   ├── Sticky navbar spacing (56px)
│   ├── Scroll shadow effect
│   ├── Off-canvas mobile sidebar
│   ├── Touch-friendly link sizing
│   ├── Backdrop overlay (60% opacity)
│   ├── Active page highlighting (#c9849e)
│   ├── Hamburger button enhancements
│   └── Print styles
│
└── banner-parallax.css
    ├── Full-width parallax banners
    ├── Auto-contrast classes (light-text, dark-text)
    ├── Responsive sizing (300px → 200px → 150px)
    └── Gradient overlay for readability
```

### JavaScript Enhancements
1. **Scroll shadow detection** - Adds `.scrolled` class when `window.scrollY > 10`
2. **Active page highlighting** - URL path matching for nav links
3. **Auto-close off-canvas** - Hides sidebar on link click (mobile)
4. **Banner brightness analysis** - Canvas-based image sampling for text contrast

### Bootstrap 5 Integration
- Uses native `offcanvas` component (not collapse)
- `data-bs-toggle="offcanvas"` trigger
- `offcanvas-start` for left-side slide
- Desktop override: Off-canvas acts as regular flex container at `lg` breakpoint

## Issue Requirements Checklist

| # | Requirement | Status |
|---|-------------|--------|
| 1 | Banner graphic per CMS page, parallax scrolling | ✅ Done |
| 2 | Graceful degradation without banner | ✅ Done |
| 3 | Navbar hovers left side on mobile, bigger fonts, active highlighting | ✅ Done |
| 4 | Navbar always floating at top | ✅ Done |
| 5 | Navbar NOT in print versions | ✅ Done |
| 6 | Banner scrolls at different rate (parallax) | ✅ Done |
| 7 | Text color auto-contrast with banner | ✅ Done |

## Usage

### Adding a Banner to a CMS Page
1. Navigate to Django Admin → CMS → Pages
2. Select a page to edit
3. Scroll to "Banner Image" section (collapsed by default)
4. Upload an image (recommended: 1920x400 or wider)
5. Save - banner will display with parallax effect

### Best Practices for Banners
- Use wide aspect ratio images (5:1 or wider)
- High contrast subjects work best with auto-contrast
- File size: optimize images to < 500KB for performance
- Format: JPEG for photos, PNG for graphics

## Testing

### E2E Test
`e2e_tests/e2e/test_basic_setup.py::TestPlaywrightSetup::test_navbar_toggle_works_on_mobile`
- Verifies off-canvas opens/closes properly
- Tests hamburger button, sidebar visibility, close button

### Manual Testing
1. Resize browser to mobile width (< 992px)
2. Click hamburger menu - sidebar should slide from left
3. Verify 60% dark backdrop overlay
4. Click a nav link - sidebar should auto-close
5. Click close button - sidebar should hide

## Related Issues
- Issue #322: TinyMCE table overflow (related CSS patterns)
- Issue #377: Bootstrap navbar toggle (foundation for this work)

## Commits
- `ca5d916` - Issue #547: Site style enhancements - sticky navbar and banner images
- `4eb77ff` - Issue #547: Mobile off-canvas sidebar navigation
- (pending) - Issue #547: Off-canvas backdrop styling and documentation
