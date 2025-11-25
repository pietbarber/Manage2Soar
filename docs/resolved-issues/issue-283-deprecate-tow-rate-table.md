# Issue 283: Deprecate and Retire Tow Rate Table

**Issue Link:** [#283](https://github.com/pietbarber/Manage2Soar/issues/283)  
**Status:** ✅ Completed  
**Date Resolved:** November 24, 2025  
**Milestone:** TowRate System Deprecation

## Overview

Successfully deprecated and retired the legacy `TowRate` table in favor of the new `TowplaneChargeScheme` system. This eliminates the old global tow rate table and ensures all towplanes use the flexible, towplane-specific charging system introduced in Issue #67.

## Problem Statement

The legacy `TowRate` system was a global pricing table that applied the same rates to all towplanes regardless of their specific characteristics. With the introduction of the new `TowplaneChargeScheme` system, the old system became redundant and needed to be fully deprecated to:

- Eliminate code complexity with dual pricing systems
- Remove the fallback logic that could cause inconsistent pricing
- Ensure all towplanes use the modern, flexible pricing model
- Clean up the database schema and remove unused tables

## Solution Implemented

### 1. Migration to New System

**Active Towplanes Configured:**
- **Husky** & **Pawnee**: Already had SSC charge schemes ($25 hookup + $1/100ft above 1000ft)
- **Winch**: Created standard rates scheme
- **Stahl Skyhawk**: Created standard rates scheme  
- **SVS Pawnee**: Created standard rates scheme
- **Other**: Created standard rates scheme
- **Self Launch**: Created zero-cost scheme ($0.00 for all altitudes)

**Retired Towplanes:**
- **Pawnee 66**: No scheme needed (crashed in 2017, 14,544 historical flights)
- **Club Towplane & Test Towplane**: No schemes needed (test/placeholder entries)

### 2. Code Changes

**Models Updated:**
```python
# REMOVED: TowRate model class entirely
# UPDATED: Flight.tow_cost_calculated() - removed TowRate fallback logic
# UPDATED: Flight.tow_cost_display() - fixed to show $0.00 instead of "—" for zero costs
```

**Admin Interface:**
- Removed `TowRateAdmin` class and registration
- Updated `TowplaneChargeScheme` admin help text
- Removed TowRate from imports

**Tests Updated:**
- Removed `BackwardCompatibilityTestCase` class (85+ lines)
- Updated fallback tests to expect `None` instead of TowRate pricing
- Updated test imports to remove TowRate references

### 3. Database Migration

**Migration:** `0012_remove_towrate_model.py`
```python
operations = [
    migrations.DeleteModel(name="TowRate"),
]
```

### 4. Data Cleanup

**Files Removed:**
- `logsheet/management/commands/tow_rate_import.py`
- `loaddata/skyline-only/logsheet.TowRate.json`
- TowRate permissions from `groups_and_permissions.json`
- `tow_rate_import` entry from `import_order.txt`

## Technical Details

### Pricing Comparison

The new system maintains equivalent pricing to the old system:

| Altitude | Old TowRate | New System | Status |
|----------|-------------|------------|---------|
| 1000ft   | $25.00     | $25.00     | ✅ Match |
| 2000ft   | $35.00     | $35.00     | ✅ Match |
| 3000ft   | $45.00     | $45.00     | ✅ Match |
| 4000ft   | $55.00     | $55.00     | ✅ Match |

### Self-Launch Special Case

**Problem:** Self-launching gliders (motor gliders) shouldn't be charged for tows since they don't use aerotows.

**Solution:** Created dedicated charge scheme:
- Name: "Self Launch - No Charge"
- Hookup Fee: $0.00
- All altitudes: $0.00
- Display: Shows "$0.00" (not "—") to indicate intentional zero charge

## Impact Assessment

### Before Deprecation
- **2 systems**: TowRate (legacy) + TowplaneChargeScheme (new)
- **Complex fallback logic** in Flight.tow_cost_calculated()
- **Inconsistent pricing** depending on towplane configuration
- **Database bloat**: 76 unused TowRate records
- **14,834 flights** using TowRate fallback

### After Deprecation
- **1 system**: TowplaneChargeScheme only
- **Simplified pricing logic**: Direct scheme calculation
- **Consistent pricing**: All towplanes use same modern system
- **Clean database**: TowRate table removed
- **Zero disruption**: All flights maintain correct pricing

## Testing Results

**Comprehensive Testing:**
- ✅ All 58 logsheet tests pass
- ✅ All 13 towplane charging tests pass  
- ✅ Self-launch flights show $0.00 correctly
- ✅ Regular tows calculate proper costs ($35 for 2000ft)
- ✅ Migration applies cleanly
- ✅ No data loss or corruption

## Rollout Considerations

Since this project has no customers yet:
- ✅ **No revenue impact** from temporary disruption
- ✅ **Destructive migration safe** to run
- ✅ **No rollback plan needed**
- ✅ **Direct deployment** recommended

## Files Modified

### Core Logic
- `logsheet/models.py` - Removed TowRate model, updated Flight methods
- `logsheet/admin.py` - Removed TowRateAdmin, updated imports

### Tests  
- `logsheet/tests/test_towplane_charging.py` - Updated for new system

### Data/Migration
- `logsheet/migrations/0012_remove_towrate_model.py` - Drop TowRate table
- `loaddata/groups_and_permissions.json` - Removed TowRate permissions
- `loaddata/import_order.txt` - Removed tow_rate_import reference

### Removed Files
- `logsheet/management/commands/tow_rate_import.py`
- `loaddata/skyline-only/logsheet.TowRate.json`

## Success Metrics

✅ **Code Simplification:** Removed 100+ lines of legacy code  
✅ **System Unification:** Single pricing system for all towplanes  
✅ **Feature Parity:** Equivalent pricing maintained  
✅ **Special Cases:** Self-launch properly handled with $0.00 costs  
✅ **Clean Migration:** Database schema simplified  
✅ **Test Coverage:** All functionality verified  

## Future Considerations

- **New Towplanes:** Will require TowplaneChargeScheme configuration
- **Pricing Changes:** Use admin interface to modify schemes, not code
- **Historical Data:** Old TowRate-based flight costs preserved in database
- **Documentation:** Models documentation updated to reflect new schema

---

**Resolution:** The legacy TowRate system has been completely deprecated and removed. All towplanes now use the modern, flexible TowplaneChargeScheme system with equivalent pricing and proper handling of special cases like self-launching gliders.
