# Analytics App

The **Analytics** app provides read-only, presentation-grade charts for club operations. It pulls data from existing apps (e.g., `logsheet`, `members`) and renders interactive charts with Chart.js. Every chart supports **PNG | SVG | CSV** export.

- **Audience:** any authenticated member (admins see everything; regular members see finalized ops unless “Include unfinalized” is checked).
- **Route:** `/analytics/`
- **Nav:** included via the main navbar.

---

## Quick Start

1. Ensure static assets are available:
    
    ```bash
    python manage.py collectstatic
    ```

2. Visit `/analytics/`.
3. Use the **Annual** controls to set year range, or the **Date range** picker for period charts.
4. Use the buttons in each chart’s top-right corner to **download PNG/SVG/CSV**.

---

## Pages & Permissions

- `analytics.views.dashboard` (decorated with `@active_member_required`)
  - Superusers bypass membership checks.
  - Non-superusers must have allowed membership statuses (from `members.decorators`).

---

## URL Parameters

**Annual charts:**
- `start` *(int)* – first year (e.g., `2011`)
- `end` *(int)* – last year (e.g., `2025`)
- `all=1` – include unfinalized logs (otherwise finalized only)

**Date-range charts:**
- `util_start` *(YYYY-MM-DD)*
- `util_end` *(YYYY-MM-DD)*

**Examples:**
- `/analytics/?start=2012&end=2025`
- `/analytics/?start=2016&end=2024&all=1`
- `/analytics/?util_start=2025-07-01&util_end=2025-08-22`

> If a parameter is omitted, a sensible default is applied by the view (e.g., current year / recent period).

---

## Charts

### Annual (based on `start`/`end`)
1. **Cumulative Flights by Julian Day**
   - Each year is a line; current year emphasized.
   - Current-year line **stops after “today”** (no fictitious flat line).
   - **Zero-flight years are not plotted.**
   - Tooltip includes day-of-year and calendar date.

2. **Flights by Year by Aircraft (stacked)**
   - Club ships shown individually.
   - Non-club ships bucketed as **Private**.
   - Flights with `glider=None` bucketed as **Unknown**.
   - Low-volume tails grouped as **Other** (when applicable).

### Date range (based on `util_start`/`util_end`)
3. **Glider Utilization**
   - Horizontal grouped bars: **Flights**, **Hours**, **Avg minutes** per ship.
4. **Private Glider Utilization**
   - Same as above, but **excludes club-owned** ships.
5. **Flying Days by Member**
   - Days with any flying activity (≥ 2 days threshold applied in query).
   - Uses `full_display_name`.
6. **Glider Flights by Pilot (non-instruction)**
   - Counts per pilot (≥ 2 flights threshold).
7. **Flight Duration Distribution (survival-style)**
   - X = hours, Y = **Percent of flights (≥ x)** with **0% at top, 100% at bottom**.
   - Blue region fills downward from 0% to the curve.
   - Status line shows median and % over 1/2/3 hours.
8. **Instructor Flights (by weekday)**
   - Horizontal stacked bars (Mon→Sun).
9. **Tow-pilot Flights (by weekday)**
   - Horizontal stacked bars (Mon→Sun).
10. **Long Flights (≥ 3 hours) by Pilot**
   - Counts per pilot; status shows longest flight (h:mm).
11. **DO & ADO Assignment Days**
   - Horizontal **stacked** bars: DO vs ADO distinct ops-days.

All charts include **PNG | SVG | CSV** export:
- **PNG:** high-DPI via Chart.js.
- **SVG:** PNG wrapped inside an SVG container (great for slides).
- **CSV:** labels and series values, or `(x,y)` for XY charts.

---

## Data Sources

- **Flights**: `logsheet.models.Flight`
  - Uses `logsheet.log_date` for ops day.
  - “Landed” filter: both `launch_time` and `landing_time` not null.
  - Duration: `Flight.duration` fallback to `landing_time - launch_time`.
  - Instruction = `instructor` not null.
- **Gliders**: `logsheet.models.Glider`
  - `club_owned` boolean determines *club vs private* buckets.
- **Logsheets**: `logsheet.models.Logsheet`
  - Duty assignments: `duty_officer`, `assistant_duty_officer`.
  - `finalized` flag governs inclusion when `all` is not set.

> “Unknown” glider = flights where `glider_id IS NULL` (common for legacy “Private” entries that didn’t map to a specific ship).

---

## Implementation Notes

- **Template:** `templates/analytics/dashboard.html`
- **Query helpers:** `analytics/queries.py` (all aggregation lives here)
- **Frontend:**
  - **JS:** `static/analytics/charts.js` (single initializer, exported helpers)
  - **CSS:** `static/analytics/analytics.css` (heights, toolbar placement, theme tokens)
  - **Library:** Chart.js (CDN)
  - **Data handoff:** one `analytics_data` JSON blob (`{% json_script %}`) consumed by `charts.js`

### The `analytics_data` blob (shape)
    
```json
{
  "cumulative": { "labels": [1,2,3], "years": [2011], "data": {"2011":[0,1,2]}, "totals": {"2011": 1234}, "instr": {"2011": 321}, "current_year": 2025 },
  "by_acft": { "years":[2011], "cats":["N123AB","Private","Unknown","Other"], "matrix": {"N123AB":[10], "Private":[5]} },
  "util":      { "names":["N123AB"], "flights":[10], "hours":[7.5], "avgm":[45] },
  "util_priv": { "names":["N321CD"], "flights":[6],  "hours":[3.2], "avgm":[32] },
  "fdays":     { "names":["Alex"], "days":[8], "ops_total": 87 },
  "pgf":       { "names":["Blake"], "counts":[12] },
  "duration":  { "points":[{"x":0.1,"y":99.5}], "median_min": 32, "pct_gt": {"1":17,"2":4,"3":1} },
  "instructors": { "names":["Casey"], "labels":["Mon","Tue"], "matrix":{"Mon":[3],"Tue":[2]}, "inst_total": 456, "all_total": 2100 },
  "tows":        { "names":["Drew"],  "labels":["Mon","Tue"], "matrix":{"Mon":[4],"Tue":[3]}, "tow_total": 980 },
  "long3h":    { "names":["Evan"], "counts":[2], "longest_min": 245, "threshold_hours": 3.0 },
  "duty":      { "names":["Fin"], "labels":["DO","ADO"], "matrix":{"DO":[2], "ADO":[1]}, "totals":[3], "do_total": 40, "ado_total": 22, "ops_days_total": 95 }
}
```

---

## Styling

- All layout/positioning lives in `analytics.css`:
  - `.chart-card`, `.chart-tools`, `.chart-title-pad`
  - `.chart-box`, with size modifiers: `--short`, `--tall`, `--xl`
- Theme tokens: `--chart-text`, `--chart-grid` adapt to light/dark.

---

## Performance

- Suggested indexes:
  - `Logsheet(log_date)`, `Logsheet(finalized)`
  - `Flight(logsheet_id)`, `Flight(glider_id)`
  - `Flight(pilot_id)`, `Flight(instructor_id)`
  - `Flight(launch_time, landing_time)`

---

## Troubleshooting

- **FieldError: `landing`** → use `landing_time` / `launch_time` and `logsheet__log_date`.
- **Unsupported lookup `date`** → annotate `ops_date=F("logsheet__log_date")` then extract year/DOY.
- **`json_script` not found** → `{% load json_script %}` in the template.
- **Chart doesn’t render** → verify `analytics_data` blob; empty arrays skip init and show a status line.
- **`destroy` is not a function`** → guard with `if (chart?.destroy) chart.destroy()`.
- **`makeHBar is not defined`** → export helpers (Option B) and don’t overwrite `window.AnalyticsCharts`.

---

## Development Tips

- Adding a new chart:
  1. Write a query helper in `queries.py`.
  2. Add the data to `analytics_data` in the view.
  3. Add a `<canvas>` card + toolbar in the template.
  4. Implement an initializer in `charts.js`.

- Export buttons auto-bind to any `.chart-tools` group (PNG/SVG/CSV).

---

## Changelog

- **2025-08** Initial release: annual + date-range charts, export buttons, CSS theming.
