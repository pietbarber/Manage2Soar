# Bootstrap5 Modernization Style Guide
*Created from the successful modernization of members pages (Issue #247)*

## 🎨 Visual Design Philosophy

### Color Palette & Theme
- **Primary Brand Colors**: Bootstrap's primary blue (`bg-primary`, `text-primary`) for headers and main actions
- **Status Color System**:
  - Success: `bg-success` (green) for active/positive states
  - Warning: `bg-warning text-dark` for pending/caution states  
  - Danger: `bg-danger` (red) for inactive/negative states
  - Secondary: `bg-secondary` for neutral/disabled states
  - Info: `bg-info` for informational content

### Typography Hierarchy
```html
<!-- Page Headers -->
<h1 class="display-6 fw-bold text-primary mb-1">
  <i class="bi bi-[icon] me-2"></i>Page Title
</h1>
<p class="text-muted mb-0">Descriptive subtitle</p>

<!-- Section Headers -->
<h6 class="fw-bold text-primary mb-3">
  <i class="bi bi-[icon] me-2"></i>Section Title
</h6>
```

## 🏗️ Layout Patterns

### Card-Based Design
Replace tables with responsive card grids:
```html
<div class="row g-4" id="contentGrid">
  <div class="col-xl-4 col-lg-6 col-md-6">
    <div class="card h-100">
      <div class="card-body">
        <!-- Card content -->
      </div>
    </div>
  </div>
</div>
```

### Search & Filter Section
```html
<!-- Search Section -->
<div class="search-section">
  <div class="row">
    <div class="col-lg-6 mx-auto">
      <div class="input-group input-group-lg">
        <span class="input-group-text bg-white border-end-0">
          <i class="bi bi-search text-muted"></i>
        </span>
        <input type="text" class="form-control search-input border-start-0"
               placeholder="Search..." id="liveSearch">
      </div>
    </div>
  </div>
</div>

<!-- Filter Section -->
<div class="filter-section">
  <form method="get" id="filterForm">
    <!-- Filter controls here -->
    <div class="row mt-3">
      <div class="col-12 text-center">
        <button type="submit" class="btn btn-primary btn-modern me-2">
          <i class="bi bi-funnel me-2"></i>Apply Filters
        </button>
        <a href="current_url" class="btn btn-outline-secondary btn-modern">
          <i class="bi bi-arrow-clockwise me-2"></i>Reset
        </a>
      </div>
    </div>
  </form>
</div>
```

### Accordion Sections (for detail pages)
```html
<div class="accordion accordion-modern" id="contentAccordion">
  <div class="accordion-item">
    <h2 class="accordion-header">
      <button class="accordion-button" type="button" data-bs-toggle="collapse"
              data-bs-target="#section1">
        <i class="bi bi-[icon] me-2"></i>Section Title
      </button>
    </h2>
    <div id="section1" class="accordion-collapse collapse show">
      <div class="accordion-body">
        <!-- Section content -->
      </div>
    </div>
  </div>
</div>
```

## 🎯 Component Patterns

### Modern Buttons
```html
<!-- Primary Actions -->
<button class="btn btn-primary btn-modern">
  <i class="bi bi-[icon] me-2"></i>Action Text
</button>

<!-- Secondary Actions -->
<button class="btn btn-outline-secondary btn-modern">
  <i class="bi bi-[icon] me-2"></i>Action Text
</button>
```

### Badge System
Replace emojis with semantic badges:
```html
<!-- Status Badges -->
<span class="badge bg-success">Active</span>
<span class="badge bg-warning text-dark">Pending</span>
<span class="badge bg-danger">Inactive</span>

<!-- Role/Feature Badges -->
<span class="badge bg-primary me-1">
  <i class="bi bi-[icon]"></i> Role Name
</span>
```

### Contact Information Cards
```html
<div class="card contact-info mb-4">
  <div class="card-header bg-primary text-white">
    <h5 class="mb-0">
      <i class="bi bi-[icon] me-2"></i>Section Title
    </h5>
  </div>
  <div class="card-body">
    <div class="row g-3">
      <div class="col-md-6">
        <div class="contact-item">
          <div class="contact-label">
            <i class="bi bi-envelope text-primary me-2"></i>
            <strong>Email</strong>
          </div>
          <div class="contact-value">
            <a href="mailto:email" class="text-decoration-none">email</a>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>
```

## 🎨 Custom CSS Patterns

### App-Specific CSS Files
Create `static/css/[app_name].css` for each app with these patterns:

```css
/* Modern Card Styling */
.[app]-card {
  border: none;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.[app]-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 15px rgba(0, 0, 0, 0.15);
}

/* Modern Button Styling */
.btn-modern {
  border-radius: 8px;
  font-weight: 600;
  padding: 0.75rem 1.5rem;
  transition: all 0.2s ease;
}

.btn-modern:hover {
  transform: translateY(-1px);
}

/* Search Section Styling */
.search-section {
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  padding: 2rem 1rem;
  margin: 2rem -1rem;
  border-radius: 15px;
}

.search-input {
  border-radius: 25px;
  padding: 0.75rem 1rem;
}

/* Filter Section Styling */
.filter-section {
  background: white;
  padding: 1.5rem;
  border-radius: 10px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  margin-bottom: 2rem;
}

/* Contact Information Cards */
.contact-info {
  border-left: 4px solid var(--bs-primary);
}

.contact-item {
  padding: 0.75rem 0;
  border-bottom: 1px solid #f1f3f4;
}

.contact-item:last-child {
  border-bottom: none;
}

.contact-label {
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
}

.contact-value {
  font-size: 1rem;
}

/* Back to Top Button */
.back-to-top {
  position: fixed;
  bottom: 2rem;
  right: 2rem;
  width: 50px;
  height: 50px;
  background: var(--bs-primary);
  color: white;
  border: none;
  border-radius: 50%;
  font-size: 1.2rem;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: all 0.3s ease;
  z-index: 1000;
}

.back-to-top:hover {
  background: var(--bs-primary);
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
}

/* Responsive Design */
@media (max-width: 768px) {
  .search-section {
    margin: 1rem -0.5rem;
    padding: 1.5rem 1rem;
  }

  .filter-section {
    margin: 1rem -0.5rem;
    padding: 1rem;
  }
}
```

## 🛠️ JavaScript Patterns

### Live Search Implementation
```javascript
document.addEventListener('DOMContentLoaded', function() {
    // Live search functionality
    const searchInput = document.getElementById('liveSearch');
    const items = document.querySelectorAll('.searchable-item');

    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const searchTerm = this.value.toLowerCase();

            items.forEach(function(item) {
                const searchableText = item.dataset.searchText || '';

                if (searchableText.includes(searchTerm)) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        });
    }
});
```

### Selective Auto-Submit for Filters
```javascript
// Only auto-submit specific filter types (not all checkboxes)
const autoSubmitCheckboxes = document.querySelectorAll('#filterForm input[name="specific_filter"]');
autoSubmitCheckboxes.forEach(function(checkbox) {
    checkbox.addEventListener('change', function() {
        clearTimeout(window.filterTimeout);
        window.filterTimeout = setTimeout(function() {
            document.getElementById('filterForm').submit();
        }, 300);
    });
});
```

## 🏷️ Icon Usage (Bootstrap Icons)

### Semantic Icon Mapping
- **People/Members**: `bi-people`, `bi-person`, `bi-person-plus`
- **Search**: `bi-search`
- **Filters**: `bi-funnel`
- **Contact**: `bi-envelope`, `bi-telephone`, `bi-phone`, `bi-geo-alt`
- **Actions**: `bi-pencil-square`, `bi-eye`, `bi-trash`, `bi-plus-circle`
- **Navigation**: `bi-arrow-left`, `bi-arrow-right`, `bi-chevron-left`, `bi-chevron-right`
- **Status**: `bi-check-circle`, `bi-exclamation-triangle`, `bi-info-circle`
- **Privacy**: `bi-shield-exclamation`, `bi-eye-slash`

## 📱 Responsive Design Principles

### Grid Breakpoints
```html
<!-- Cards responsive layout -->
<div class="col-xl-4 col-lg-6 col-md-6">  <!-- 3-2-1 columns -->
<div class="col-xl-3 col-lg-4 col-md-6">  <!-- 4-3-2 columns -->
<div class="col-xl-6 col-lg-6 col-md-12"> <!-- 2-2-1 columns -->
```

### Mobile-First Approach
- Design for mobile first, enhance for desktop
- Use `d-none d-md-block` to hide non-essential elements on mobile
- Stack vertically on small screens, horizontal on larger screens

## 🔄 Implementation Checklist for Each App

### Phase 1: Structure & Layout
- [ ] Replace table layouts with responsive card grids
- [ ] Add search functionality with live filtering
- [ ] Implement filter section with proper UX (manual vs auto-submit)
- [ ] Create app-specific CSS file in `static/css/[app].css`
- [ ] Add CSS reference to base template or app templates

### Phase 2: Components & Styling
- [ ] Replace emojis with Bootstrap badges and icons
- [ ] Modernize buttons with `btn-modern` class
- [ ] Add hover effects and smooth transitions
- [ ] Implement contact-style information cards
- [ ] Add back-to-top button for long pages

### Phase 3: Details & Polish
- [ ] Add accordion sections for complex detail pages
- [ ] Implement consistent color scheme and typography
- [ ] Add proper loading states and transitions
- [ ] Test responsive design on all screen sizes
- [ ] Add accessibility improvements (aria-labels, etc.)

## 📝 Issue Template for Future Bootstrap5 Modernization

**Title**: "Bootstrap5 Modernization: [App Name] Pages"

**Description**:
```
## Objective
Modernize the [app_name] pages to match the Bootstrap5 design system established in Issue #247 (members pages).

## Pages to Update
- [ ] List page (e.g., /app/list/)
- [ ] Detail view page (e.g., /app/123/view/)  
- [ ] [Any other relevant pages]

## Design Requirements
Follow the Bootstrap5 Modernization Style Guide (docs/bootstrap5-modernization-guide.md):

### Visual Changes
- [ ] Replace table layouts with responsive card grids
- [ ] Replace emojis with Bootstrap badges and icons
- [ ] Add live search functionality
- [ ] Implement modern filter section with proper UX
- [ ] Add hover effects and smooth transitions

### Technical Changes  
- [ ] Create app-specific CSS file: `static/css/[app].css`
- [ ] Update templates to use Bootstrap5 components
- [ ] Add proper responsive design (mobile-first)
- [ ] Implement JavaScript for live search and selective auto-submit
- [ ] Add back-to-top button for long pages

### Specific [App] Considerations
[Add any app-specific requirements, unique data structures, or special UI needs]

## Success Criteria
- [ ] Pages load without errors
- [ ] Design matches the modern look established in members pages
- [ ] All functionality preserved and enhanced
- [ ] Responsive design works on mobile, tablet, desktop
- [ ] Live search works correctly
- [ ] Filter UX is intuitive (manual submit where appropriate)

## Reference
- Base implementation: Issue #247 - Members pages modernization
- Style guide: `docs/bootstrap5-modernization-guide.md`
- Example CSS: `static/css/members.css`
- Example templates: `members/templates/members/`
```

This comprehensive style guide captures the exact patterns, components, and approach I used for the members pages. Following this guide will ensure consistent, beautiful modernization across your entire site! 🚀
