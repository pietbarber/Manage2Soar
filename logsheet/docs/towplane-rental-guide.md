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

### During Logsheet Closeout
When closing out a logsheet that includes non-towing towplane usage:

1. Navigate to the **Logsheet Closeout** page
2. In the **Towplane Summary** section, find the relevant towplane
3. Fill out the standard fields:
   - Start Tach
   - End Tach  
   - Fuel Added
4. **New**: Enter **Rental Hours (Non-Towing)** - the number of hours to be charged as rental
5. **New**: Select **Charged To** - the member responsible for paying the rental costs
6. Add notes describing the rental usage (e.g., "Flight review", "Sightseeing flight")

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
- Closeout templates display rental information
- Financial templates show towplane rental costs alongside flight costs

## Migration Notes
- Issue #123 adds new database fields via Django migrations
- Existing logsheets are not affected
- Rental rates need to be configured manually via admin interface
- No data migration required as this is a new feature
