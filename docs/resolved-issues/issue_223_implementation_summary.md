# Issue #223: Duty Roster Operational Calendar Implementation

## Problem Solved
The duty roster generation system was generating all weekend dates for a given month, but clubs need to:
1. Configure when their operational season runs (e.g., "First weekend of May" through "Second weekend of December")
2. Easily remove unwanted dates from proposed rosters (e.g., remove the last 2 weekends of December)

## Solution Implemented

### 1. Operational Calendar Configuration
**Added to SiteConfiguration model:**
- `operations_start_period`: Text field (e.g., "First weekend of May")
- `operations_end_period`: Text field (e.g., "Second weekend of December")

**Admin Interface:**
- New "Operational Calendar" fieldset in Django admin
- Clear descriptions and examples
- Collapsible section for organization

### 2. Smart Weekend Calculation
**Created `duty_roster/operational_calendar.py`:**
- `get_operational_weekend()`: Converts text like "First weekend of May" into actual dates
- Handles edge cases correctly (e.g., May 1st on Sunday includes April 30th)
- Supports: First, Second, Third, Fourth, Last weekend of any month
- Year-agnostic: automatically calculates for any year

**Examples:**
- "First weekend of May 2022" (May 1st = Sunday) → April 30-May 1
- "First weekend of May 2021" (May 1st = Saturday) → May 1-2
- "Second weekend of December 2025" → December 13-14

### 3. Enhanced Roster Generation
**Modified `duty_roster/roster_generator.py`:**
- `is_within_operational_season()`: Checks if a date falls within configured season
- Automatic filtering during roster generation
- Logging of filtered dates for debugging

### 4. Enhanced Propose Roster Interface
**Enhanced `propose_roster` view and template:**

**New Features:**
- Shows operational calendar configuration and season boundaries
- Lists dates that were automatically filtered out and why
- Easy date removal: checkboxes to remove specific dates from proposed roster
- Clear visual feedback about what's included/excluded

**Workflow:**
1. Rostermeister clicks "Generate Roster"
2. System shows proposed dates (automatically filtered by operational season)
3. System displays which dates were excluded and why
4. Rostermeister can check boxes to remove additional specific dates
5. "Remove Selected Dates" button removes unwanted dates
6. "Accept & Publish" finalizes the roster

### 5. Management Command for Testing
**Created `test_roster_generation` management command:**
```bash
python manage.py test_roster_generation --month=12 --show-config
```
- Shows current operational configuration
- Tests roster generation for any month/year
- Displays season boundaries and filtering results
- Provides configuration format examples

## Use Cases Solved

### Your Club (First weekend of May through Second weekend of December):
- **December roster generation**: Automatically includes only Dec 6-7 and Dec 13-14
- **Manual exclusion**: Rostermeister can easily remove Dec 13-14 if needed
- **No November ops**: November automatically excluded

### Other Clubs:
- **Different seasons**: "Second weekend of April" through "Last weekend of October"
- **Year-round ops**: Leave fields blank to include all dates
- **Custom periods**: Any combination of ordinal (First/Second/Third/Fourth/Last) + month

## Technical Implementation

### Files Modified:
- `siteconfig/models.py`: Added operational calendar fields
- `siteconfig/admin.py`: Added admin interface fieldset
- `duty_roster/operational_calendar.py`: New weekend calculation logic
- `duty_roster/roster_generator.py`: Added seasonal filtering
- `duty_roster/views.py`: Enhanced propose_roster view
- `duty_roster/templates/propose_roster.html`: Enhanced UI
- `duty_roster/management/commands/test_roster_generation.py`: Testing command

### Database Migration:
- `siteconfig/migrations/0009_*`: Adds new operational calendar fields

## Testing Results

**December 2025 with "Last weekend of October" end:**
- All 8 weekend dates filtered out ✅
- Zero roster entries generated ✅

**December 2025 with "Second weekend of December" end:**
- First 2 weekends included (Dec 6-7, Dec 13-14) ✅  
- Last 2 weekends filtered out (Dec 20-21, Dec 27-28) ✅

**May 2025 with "First weekend of May" start:**
- Starts from May 3-4 (correct first weekend) ✅
- All subsequent May weekends included ✅

## Issue Status: ✅ RESOLVED

Both success criteria from Issue #223 have been fully implemented:

1. ✅ **Operational calendar configuration**: Site admins can configure when club operations run using natural language (e.g., "First weekend of May")

2. ✅ **Easy date removal**: Rostermeister can easily remove unwanted dates from proposed rosters using checkboxes and a "Remove Selected Dates" button

The system now handles the December scenario perfectly: generates only the desired weeks automatically, and provides an easy way to remove additional dates if needed.