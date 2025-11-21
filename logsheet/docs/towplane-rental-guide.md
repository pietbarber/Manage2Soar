# Towplane Rental Feature - User Guide

## Overview
As of Issue #123, Manage2Soar now supports tracking and billing for non-towing towplane usage such as:
- Sightseeing flights
- Flight reviews
- Aircraft retrieval missions
- Training flights

## Setting Up Towplane Rental Rates

### Admin Configuration
1. Navigate to **Admin → Towplanes** in the Django admin interface
2. Select the towplane you want to configure
3. In the "Rental Rates" section, enter the **Hourly Rental Rate** in USD per hour
4. Save the changes

Example rates:
- Husky: $95.00/hour
- Pawnee: $85.00/hour

## Recording Towplane Rental Usage

### Manual Towplane Addition
For non-towing operations where no flights were logged (e.g., Biff's personal flight to Roanoke):

1. Navigate to the **Logsheet Closeout** page
2. In the **Towplane Closeout** section, find the **"Add Towplane for Rental Usage"** card
3. Select the desired towplane from the dropdown (shows rental rates)
4. Click **"Add Towplane"** button
5. The towplane form will appear with all rental tracking fields

### During Logsheet Closeout
When closing out a logsheet that includes non-towing towplane usage:

1. Navigate to the **Logsheet Closeout** page
2. In the **Towplane Summary** section, find the relevant towplane (or add manually if needed)
3. Fill out the standard fields:
   - Start Tach
   - End Tach  
   - Fuel Added
4. **New**: Enter **Rental Hours (Non-Towing)** - the number of hours to be charged as rental
5. **New**: Select **Charged To** - the member responsible for paying the rental costs
6. Add notes describing the rental usage (e.g., "Flight review", "Sightseeing flight")

### UI Improvements
- **Bootstrap5 Styling**: All duty crew dropdowns use modern `form-select` styling
- **Clean Interface**: Towplane selector hidden in individual cards (towplane name shown in header)
- **Smart Filtering**: "Add Towplane" only shows towplanes not already in the closeout form
- **Improved Workflow**: Form submissions stay on closeout page for continued editing

### Important Notes
- **Rental Hours ≠ Total Tach Time**: Only enter the hours that should be charged as rental
- **Mixed Usage**: If a towplane did both towing and rental on the same day, only enter the rental portion in the "Rental Hours" field
- **Member Selection**: The "Charged To" member must be selected for rental charges to appear in financial calculations

## Financial Integration

### Cost Calculation
The system automatically calculates rental costs as:
```
Rental Cost = Rental Hours × Towplane Hourly Rate
```

### Payment Tracking
- Towplane rental costs appear in the **Logsheet Finances** page
- Rental charges are added to the responsible member's total bill
- Payment methods can be tracked the same way as flight costs (cash, check, Zelle, on account)

### Financial Summary
The financial summary now includes:
- **Flight Costs**: Traditional tow and glider rental costs
- **Towplane Rentals**: New section showing non-towing rental charges
- **Total**: Combined flight and towplane rental costs

## Use Case Examples

### Flight Review Scenario
**Situation**: John wants a flight review in the Husky with an instructor
**Logsheet Entry**:
- Rental Hours: 2.5 (duration of flight review)
- Charged To: John
- Notes: "Flight review with CFI Smith"
- **Cost**: 2.5 × $95.00 = $237.50

### Aircraft Retrieval
**Situation**: Towplane retrieval flight to move a glider from another airport
**Logsheet Entry**:
- Rental Hours: 1.5 (flight time for retrieval)
- Charged To: Member requesting retrieval
- Notes: "Bergfalke retrieval from Flying Cow to Woodstock"
- **Cost**: 1.5 × $95.00 = $142.50

### Sightseeing Flight
**Situation**: Tuesday non-ops day sightseeing flight
**Logsheet Entry**:
- Rental Hours: 1.2 (sightseeing flight duration)
- Charged To: Member taking sightseeing flight
- Notes: "Tuesday sightseeing flight - no glider operations"
- **Cost**: 1.2 × $95.00 = $114.00

### Mixed Operations Day
**Situation**: Normal towing operations plus one flight review
**Logsheet Entry**:
- Total Tach Time: 4.0 hours
- Rental Hours: 1.0 (only the flight review portion)
- Charged To: Member getting flight review
- Notes: "Regular towing ops plus 1 hour flight review"
- **Rental Cost**: 1.0 × $95.00 = $95.00 (towing costs handled separately)

### Personal Flight (Biff's Scenario)
**Situation**: Member takes personal flight to Roanoke on non-ops day
**Process**:
1. **No Flights Logged**: Day has no glider towing operations
2. **Manual Addition**: Duty officer uses "Add Towplane" button to add Husky
3. **Rental Entry**: 2.1 hours personal flight time recorded
4. **Member Assignment**: Charged to member taking personal flight
5. **Cost Calculation**: 2.1 × $95.00 = $199.50
6. **Conditional Validation**: Duty officer not required since no flight operations
7. **Clean Workflow**: All towplane details entered in single form without redundant dropdowns

### Personal Flight (Biff's Scenario)
**Situation**: Member takes personal flight to Roanoke on non-ops day
**Process**:
1. **No Flights Logged**: Day has no glider towing operations
2. **Manual Addition**: Duty officer uses "Add Towplane" button to add Husky
3. **Rental Entry**: 2.1 hours personal flight time recorded
4. **Member Assignment**: Charged to member taking personal flight
5. **Cost Calculation**: 2.1 × $95.00 = $199.50
6. **Conditional Validation**: Duty officer not required since no flight operations
7. **Clean Workflow**: All towplane details entered in single form without redundant dropdowns

## Business Process

### Before This Feature
- Non-towing towplane usage was tracked via paper coupon books
- Payments were mailed directly to treasurer
- No electronic record of these transactions
- Hours and charges weren't integrated into the system

### After This Feature
- All towplane usage is recorded in the electronic logsheet
- Rental charges are integrated with regular flight billing
- Complete financial tracking and reporting
- No more paper coupons for towplane rentals

## Technical Implementation

### Database Fields
- **Towplane.hourly_rental_rate**: Decimal field for hourly rental rate
- **TowplaneCloseout.rental_hours_chargeable**: Decimal field for billable rental hours
- **TowplaneCloseout.charged_to**: Foreign key to Member responsible for payment

### Calculations
- **TowplaneCloseout.rental_cost**: Property that calculates `rental_hours_chargeable × towplane.hourly_rental_rate`
- Financial views automatically include towplane rental costs in member billing

### Forms and Templates
- TowplaneCloseoutForm includes rental fields with helpful labels
- Manual towplane addition via "Add Towplane" button interface
- Bootstrap5 styling for all form elements (`form-select` class)
- Closeout templates display rental information with clean card-based layout
- Hidden towplane selector in individual forms (shown in card headers)
- Financial templates show towplane rental costs alongside flight costs
- Conditional duty officer validation for rental-only operations

## Migration Notes
- Issue #123 adds new database fields via Django migrations
- Existing logsheets are not affected
- Rental rates need to be configured manually via admin interface
- No data migration required as this is a new feature
