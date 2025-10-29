# Issue #190: Enhanced Glider Reservation System Design

## Overview
This document outlines the comprehensive glider reservation system that will transform the duty roster workflow into a full-featured club operations management system comparable to ClickNGlide functionality.

## Reservation Workflow

### Master Workflow - All Reservation Types

```mermaid
flowchart TD
    A[Member Initiates Reservation] --> B{Select Reservation Type}
    
    B --> C[Flight Instruction]
    B --> D[Solo Flight]
    B --> E[Badge Flight]
    B --> F[Check Flight]
    B --> G[Flight Review]
    B --> H[FAA Wings]
    B --> I[Other]
    
    C --> J[Select Date/Time]
    D --> J
    E --> J
    F --> J
    G --> J
    H --> J
    I --> J
    
    J --> K[Filter Available Aircraft]
    K --> L{Any Qualified Aircraft?}
    
    L -->|No| M[No Available Aircraft Notice]
    M --> N[End - No Options Available]
    
    L -->|Yes| O[Show Qualified Aircraft Only]
    O --> P[Select from Qualified List]
    P --> Q{Aircraft Available for Time?}
    
    Q -->|No| R[Show Alternative Times]
    R --> S[End - Time Conflict]
    
    Q -->|Yes| T{Time Conflict Check}
    T -->|Conflict| U[Show Conflicts]
    U --> V[Suggest Alternative Times]
    V --> O
    
    T -->|No Conflict| W{Instructor Required?}
    W -->|Yes| X[Select Instructor]
    W -->|No| Y[Create Reservation]
    
    X --> Z{Instructor Available?}
    Z -->|No| AA[Show Available Instructors]
    AA --> X
    Z -->|Yes| BB{Instructor Qualified?}
    BB -->|No| CC[Instructor Qualification Error]
    CC --> AA
    BB -->|Yes| Y
    
    Y --> DD[Create Reservation]
    DD --> EE[Status: Confirmed]
    EE --> FF[Send Confirmation]
    FF --> GG[Reservation Complete]
    
    style A fill:#e1f5fe
    style GG fill:#e8f5e8
    style N fill:#ffebee
    style S fill:#ffebee
```

### Qualification Validation Workflow

```mermaid
flowchart TD
    A[Check Member Qualifications] --> B{Rated Pilot or Student?}
    
    B -->|Student Pilot| C[Student Validation Path]
    B -->|Rated Pilot| D[Rated Pilot Validation Path]
    
    C --> E{Has Solo Endorsement?}
    E -->|No| F[Dual Instruction Only]
    E -->|Yes| G{Aircraft Type Checkout?}
    G -->|No| H[Require Aircraft Checkout]
    G -->|Yes| I{Solo Currency Current?}
    I -->|Expired| J[Require Currency Flight]
    I -->|Current| K{Single-Seater Request?}
    
    K -->|Yes - Single Seater| L{Instructor Present?}
    L -->|No| M[Student Solo - Check Weather/DO]
    L -->|Yes| N[Dual Instruction Flight]
    K -->|No - Two Seater| O{Instructor Present?}
    O -->|No| P[Student Solo Two-Seater]
    O -->|Yes| N
    
    D --> Q{Aircraft Type Qualified?}
    Q -->|No| R[Require Club Checkout]
    Q -->|Yes| S{Qualification Current?}
    S -->|Expired| T[Qualification Expired]
    S -->|Current| U{Single or Two-Seater?}
    
    U -->|Single-Seater| V[Rated Pilot Solo Flight]
    U -->|Two-Seater| W{Instruction Flight?}
    W -->|Yes| X{Member is CFI?}
    X -->|Yes| Y[Rated CFI Giving Instruction]
    X -->|No| Z[Rated Pilot Receiving Instruction]
    W -->|No| AA[Rated Pilot Recreational Flight]
    
    F --> BB[Proceed - Instructor Required]
    H --> CC[End - Aircraft Checkout Required]
    J --> DD[End - Currency Flight Required]
    M --> EE[Proceed - Student Solo Approved]
    N --> BB
    P --> EE
    R --> CC
    T --> FF[End - Qualification Expired]
    V --> GG[Proceed - Rated Solo Approved]
    Y --> HH[Proceed - CFI Instruction Approved]
    Z --> BB
    AA --> GG
    
    style BB fill:#e8f5e8
    style EE fill:#e8f5e8
    style GG fill:#e8f5e8
    style HH fill:#e8f5e8
    style CC fill:#ffebee
    style DD fill:#ffebee
    style FF fill:#ffebee
```

### Instructor Assignment Workflow

```mermaid
flowchart TD
    A[Instructor Required] --> B{Reservation Type}
    
    B -->|Flight Instruction| C[Match Training Phase]
    B -->|Flight Review| D[Require CFI-G]
    B -->|FAA Wings| E[Require Wings Qualified CFI]
    B -->|Check Flight| F[Require Check Pilot Authority]
    B -->|Badge Flight| G[Require Badge Official]
    B -->|Other| H[Admin Review Required]
    
    C --> I[Find Available CFI-G]
    D --> I
    E --> J[Find Wings CFI]
    F --> K[Find Check Pilot]
    G --> L[Find Badge Official]
    H --> M[Manual Assignment]
    
    I --> N{Instructor Available?}
    J --> N
    K --> N
    L --> N
    M --> N
    
    N -->|No| O[Request Coverage]
    N -->|Yes| P{Instructor Accepts?}
    
    O --> Q[Surge Instructor Request]
    Q --> R{Coverage Found?}
    R -->|No| S[Reschedule Required]
    R -->|Yes| T[Assign Coverage Instructor]
    
    P -->|No| U[Find Alternative]
    P -->|Yes| V[Confirm Assignment]
    
    U --> I
    T --> V
    V --> W[Instructor Assigned]
    
    S --> X[End - No Coverage]
    
    style W fill:#e8f5e8
    style X fill:#ffebee
```

### First-Come-First-Served System

The reservation system operates on a **first-come-first-served** basis with automatic confirmation upon successful validation. No approval workflows or gatekeepers required.

```mermaid
flowchart TD
    A[Reservation Request] --> B[Validate Qualifications]
    B --> C{Qualifications Met?}
    
    C -->|No| D[Show Requirements]
    D --> E[End - Qualification Required]
    
    C -->|Yes| F[Check Time Conflicts]
    F --> G{Time Available?}
    
    G -->|No| H[Show Alternative Times]
    H --> I[End - Time Conflict]
    
    G -->|Yes| J[Check Aircraft Status]
    J --> K{Aircraft Available?}
    
    K -->|No| L[Show Grounding Reason]
    L --> M[End - Aircraft Unavailable]
    
    K -->|Yes| N[Create Reservation]
    N --> O[Status: Confirmed]
    O --> P[Send Confirmation]
    P --> Q[Reservation Active]
    
    style A fill:#e1f5fe
    style Q fill:#e8f5e8
    style E fill:#ffebee
    style I fill:#ffebee
    style M fill:#ffebee
```

**Key Principles:**
- ✅ **First registered wins** - No priority system or approval hierarchy
- ✅ **Qualification validation** - System enforces member credentials automatically  
- ✅ **Time conflict prevention** - Double-booking impossible
- ✅ **Aircraft status checking** - Maintenance issues block reservations
- ✅ **Immediate confirmation** - No waiting for human approval

### Conflict Resolution Workflow

```mermaid
flowchart TD
    A[Time Conflict Detected] --> B{Conflict Type}
    
    B -->|Same Aircraft| C[Aircraft Double-Booked]
    B -->|Same Instructor| D[Instructor Double-Booked]
    B -->|Maintenance Window| E[Maintenance Conflict]
    B -->|Weather Hold| F[Weather Restriction]
    
    C --> G[Show Alternative Times]
    D --> H[Show Alternative Instructors]
    E --> I[Show Aircraft Status]
    F --> J[Show Weather Forecast]
    
    G --> K{Accept Alternative?}
    H --> L{Accept Alternative?}
    I --> M{Maintenance Complete?}
    J --> N{Weather Improves?}
    
    K -->|Yes| O[Update Reservation]
    L -->|Yes| O
    M -->|Yes| P[Clear Maintenance Flag]
    N -->|Yes| Q[Remove Weather Hold]
    
    K -->|No| R[Manual Scheduling]
    L -->|No| R
    M -->|No| S[Cancel - Maintenance]
    N -->|No| T[Cancel - Weather]
    
    P --> U[Reservation Confirmed]
    Q --> U
    O --> U
    
    R --> V{Resolution Found?}
    V -->|Yes| U
    V -->|No| W[Escalate to Admin]
    
    W --> X[Admin Intervention]
    X --> Y{Admin Decision}
    Y -->|Approve Override| U
    Y -->|Deny Request| Z[Reservation Denied]
    
    S --> Z
    T --> Z
    
    style U fill:#e8f5e8
    style Z fill:#ffebee
```

### Daily Operations Workflow

```mermaid
flowchart TD
    A[Operations Day] --> B[Pre-Flight Checks]
    B --> C{All Reservations Valid?}
    
    C -->|Yes| D[Normal Operations]
    C -->|No| E[Identify Issues]
    
    E --> F{Issue Type}
    F -->|Weather| G[Weather Briefing]
    F -->|Maintenance| H[Aircraft Status Check]
    F -->|Personnel| I[Instructor/Pilot Status]
    
    G --> J{Flyable Conditions?}
    J -->|No| K[Cancel Weather-Dependent Flights]
    J -->|Yes| L[Proceed with Caution]
    
    H --> M{Aircraft Serviceable?}
    M -->|No| N[Ground Aircraft]
    M -->|Yes| O[Release for Service]
    
    I --> P{Personnel Available?}
    P -->|No| Q[Find Substitute]
    P -->|Yes| R[Confirm Assignments]
    
    K --> S[Notify Affected Members]
    N --> T[Reassign to Other Aircraft]
    Q --> U{Substitute Found?}
    
    U -->|No| V[Cancel Affected Flights]
    U -->|Yes| W[Update Assignments]
    
    L --> X[Monitor Conditions]
    O --> Y[Normal Ops Continue]
    R --> Y
    T --> Z{Alternative Available?}
    W --> Y
    
    Z -->|No| V
    Z -->|Yes| Y
    
    D --> Y
    Y --> AA[Execute Flight Schedule]
    
    S --> BB[End - Weather Cancel]
    V --> CC[End - Personnel/Aircraft Issue]
    
    AA --> DD[Post-Flight Debrief]
    DD --> EE[Update Logbooks]
    EE --> FF[Operations Complete]
    
    style Y fill:#e8f5e8
    style AA fill:#e8f5e8
    style FF fill:#e8f5e8
    style BB fill:#fff3e0
    style CC fill:#ffebee
```

## Database Schema Design

### GliderReservation Model

```python
class GliderReservation(models.Model):
    """
    Comprehensive glider reservation system supporting various flight types,
    qualification validation, and operational safety checks.
    """
    
    # Core reservation data
    member = models.ForeignKey('members.Member', on_delete=models.CASCADE)
    glider = models.ForeignKey('logsheet.Glider', on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    # Reservation type with comprehensive options
    RESERVATION_TYPE_CHOICES = [
        ('instruction', 'Flight Instruction'),
        ('solo', 'Solo Flight'),
        ('badge', 'Badge Flight'),
        ('check', 'Check Flight'),
        ('flight_review', 'Flight Review'),
        ('faa_wings', 'FAA Wings'),
        ('other', 'Other'),
    ]
    reservation_type = models.CharField(
        max_length=20, 
        choices=RESERVATION_TYPE_CHOICES,
        help_text="Type of flight operation planned"
    )
    
    # Status tracking
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('no_show', 'No Show'),
    ]
    status = models.CharField(
        max_length=15, 
        choices=STATUS_CHOICES, 
        default='confirmed'
    )
    
    # Optional instructor assignment
    instructor = models.ForeignKey(
        'members.Member',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instruction_reservations',
        help_text="Required for instruction, review, and check flights"
    )
    
    # Additional details
    purpose = models.TextField(
        blank=True,
        help_text="Additional details about the planned flight"
    )
    special_requirements = models.TextField(
        blank=True,
        help_text="Any special equipment or setup requirements"
    )
    
    # Administrative tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['glider', 'date', 'start_time']
        ordering = ['date', 'start_time']
        indexes = [
            models.Index(fields=['date', 'glider']),
            models.Index(fields=['member', 'date']),
        ]
    
    def __str__(self):
        return f"{self.member.full_display_name} - {self.glider} on {self.date} at {self.start_time}"
    
    def clean(self):
        """Comprehensive validation for reservation requests"""
        from django.core.exceptions import ValidationError
        
        # Check if glider is grounded
        if self.glider.is_grounded:
            raise ValidationError(f"Glider {self.glider} is currently grounded for maintenance")
        
        # Validate instructor requirement for certain reservation types
        instructor_required_types = ['instruction', 'flight_review', 'faa_wings', 'check']
        if self.reservation_type in instructor_required_types and not self.instructor:
            raise ValidationError(f"Instructor required for {self.get_reservation_type_display()} flights")
        
        # Validate member qualifications for single-seater aircraft
        if self.glider.seats == 1:
            self._validate_single_seater_qualification()
        
        # Validate two-seater permissions
        elif self.glider.seats == 2:
            self._validate_two_seater_permission()
        
        # Check for time conflicts
        self._validate_time_conflicts()
        
        # Validate badge flight requirements
        if self.reservation_type == 'badge':
            self._validate_badge_flight_requirements()
    
    def _validate_single_seater_qualification(self):
        """Validate member is qualified for single-seater operations"""
        # Implementation will check member's solo endorsements and currency
        pass
    
    def _validate_two_seater_permission(self):
        """Validate member has permission for two-seater operations"""
        # Implementation will check member's dual instruction authorization
        pass
    
    def _validate_time_conflicts(self):
        """Check for overlapping reservations"""
        from django.core.exceptions import ValidationError
        
        conflicting_reservations = GliderReservation.objects.filter(
            glider=self.glider,
            date=self.date,
            status__in=['pending', 'confirmed']
        ).exclude(pk=self.pk if self.pk else None)
        
        for reservation in conflicting_reservations:
            if (self.start_time < reservation.end_time and 
                self.end_time > reservation.start_time):
                raise ValidationError(
                    f"Time conflict with existing reservation: "
                    f"{reservation.start_time}-{reservation.end_time}"
                )
    
    def _validate_badge_flight_requirements(self):
        """Validate requirements for badge flights"""
        # Badge flights typically require full-day access and specific qualifications
        if self.end_time <= self.start_time:
            from django.core.exceptions import ValidationError
            raise ValidationError("Badge flights require end time after start time")
    
    @property
    def duration_hours(self):
        """Calculate planned flight duration in hours"""
        from datetime import datetime, timedelta
        
        start_dt = datetime.combine(self.date, self.start_time)
        end_dt = datetime.combine(self.date, self.end_time)
        
        # Handle overnight flights (rare but possible)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        
        duration = end_dt - start_dt
        return duration.total_seconds() / 3600
    
    @property
    def requires_instructor(self):
        """Check if this reservation type requires an instructor"""
        instructor_required_types = ['instruction', 'flight_review', 'faa_wings', 'check']
        return self.reservation_type in instructor_required_types
    
    @property
    def is_training_flight(self):
        """Check if this is a training-related flight"""
        training_types = ['instruction', 'flight_review', 'faa_wings', 'check', 'badge']
        return self.reservation_type in training_types
```

## Reservation Type Specifications

### Flight Instruction
- **Purpose**: Primary flight training for students
- **Requirements**: Instructor required, appropriate aircraft for training phase
- **Validation**: Student must have active training record
- **Duration**: Typically 1-3 hours

### Solo Flight
- **Purpose**: Independent flight by qualified pilot
- **Requirements**: Current solo endorsement for aircraft type
- **Validation**: Member must meet currency requirements
- **Duration**: Variable based on flight plan

### Badge Flight
- **Purpose**: Official badge/rating attempts (Silver, Gold, Diamond badges)
- **Requirements**: Badge Official present, full-day aircraft access
- **Validation**: Member must meet badge prerequisites
- **Duration**: Typically full day (sunrise to sunset)

### Check Flight
- **Purpose**: Proficiency checks, rating validation, insurance requirements
- **Requirements**: Designated check pilot, specific aircraft
- **Validation**: Check pilot must be current and qualified
- **Duration**: 1-2 hours typically

### Flight Review
- **Purpose**: Biennial Flight Review (BFR) as required by FAR 61.56
- **Requirements**: CFI-G (Certified Flight Instructor - Glider)
- **Validation**: Pilot must be due for flight review
- **Duration**: Minimum 1 hour flight, 1 hour ground
- **Notes**: Required every 24 calendar months for currency

### FAA Wings
- **Purpose**: FAA Wings Pilot Proficiency Program participation
- **Requirements**: Qualified instructor, specific training objectives
- **Validation**: Member enrolled in Wings program
- **Duration**: Variable based on specific Wings credit requirements
- **Notes**: Voluntary safety program providing flight review alternatives

### Other
- **Purpose**: Miscellaneous flights not covered by standard categories
- **Requirements**: Case-by-case approval
- **Validation**: Administrative review required
- **Duration**: Variable
- **Notes**: Examples: demo flights, aircraft checkout, maintenance test flights

## Integration with Existing Systems

### Connection to Instructors App
- Link `instructor` field to qualified instructors from `instructors.models`
- Validate instructor qualifications for specific reservation types
- Track training progress for instruction reservations

### Connection to Logsheet App
- Validate against `logsheet.Glider` availability and grounding status
- Check maintenance issues before allowing reservations
- Link completed reservations to actual flight entries

### Connection to Members App
- Validate member qualifications and currency
- Check membership status and privileges
- Track member reservation history and patterns

## Validation Rules Summary

| Reservation Type | Instructor Required | Qualification Validation | Duration Limits |
|------------------|--------------------|--------------------|-----------------|
| Instruction | ✅ Yes | Training phase check | 1-4 hours |
| Solo | ❌ No | Solo endorsement | Variable |
| Badge | ❌ No* | Badge prerequisites | Full day |
| Check | ✅ Yes | Check pilot qualification | 1-3 hours |
| Flight Review | ✅ Yes (CFI-G) | BFR currency check | 2+ hours |
| FAA Wings | ✅ Yes | Wings enrollment | Variable |
| Other | ❌ No | Basic qualifications | Variable |

*Badge flights: First-come-first-served. Badge Official coordination happens outside the reservation system.

## Next Implementation Steps

1. **Create Migration**: Add `GliderReservation` model to `duty_roster` app
2. **Build Admin Interface**: Management tools for reservation oversight
3. **Create Forms**: User-friendly reservation request forms with validation
4. **Implement Views**: Reservation creation, modification, and approval workflows
5. **Build Templates**: Responsive UI for reservation management
6. **Add Permissions**: Role-based access for different reservation types
7. **Create Notifications**: Email/SMS alerts for reservation status changes
8. **Integration Testing**: Validate with existing duty roster calendar system

This comprehensive reservation system will provide the advanced scheduling capabilities requested in Issue #190 while maintaining safety and regulatory compliance.

## Critical Issue: Qualification System Odontogenesis

### Problem Statement

**Current State**: The qualification badges (`ClubQualificationType` and `MemberQualification`) are purely **visual indicators** with no enforcement mechanism. A member with an "ASK-21" badge has no actual system-enforced permission to reserve or fly the ASK-21 glider.

**Required Solution**: The qualification system requires **odontogenesis** - the development and formation of functional enforcement mechanisms that link qualification badges to specific aircraft access permissions.

### Enhanced Qualification Architecture

#### New Model: GliderQualificationRequirement

```python
class GliderQualificationRequirement(models.Model):
    """
    Links specific gliders to required qualifications for access.
    This gives "teeth" to the qualification badge system.
    """
    
    glider = models.ForeignKey('logsheet.Glider', on_delete=models.CASCADE)
    qualification = models.ForeignKey('instructors.ClubQualificationType', on_delete=models.CASCADE)
    
    # Requirement type
    REQUIREMENT_TYPE_CHOICES = [
        ('solo', 'Solo Flight Authorization'),
        ('dual', 'Dual Flight Authorization'),  
        ('either', 'Solo OR Dual Authorization'),
        ('pic', 'Pilot-in-Command Authorization'),
        ('checkout', 'Aircraft Type Checkout'),
    ]
    requirement_type = models.CharField(
        max_length=15, 
        choices=REQUIREMENT_TYPE_CHOICES,
        default='either'
    )
    
    # Optional experience constraints (configurable per club)
    minimum_hours_total = models.DecimalField(
        max_digits=6, 
        decimal_places=1, 
        null=True, 
        blank=True,
        help_text="Optional: Minimum total flight hours (club configurable)"
    )
    minimum_hours_type = models.DecimalField(
        max_digits=6, 
        decimal_places=1, 
        null=True, 
        blank=True,
        help_text="Optional: Minimum hours in this aircraft type (club configurable)"
    )
    requires_instructor_present = models.BooleanField(
        default=False,
        help_text="Instructor must be present for this aircraft"
    )
    requires_current_medical = models.BooleanField(
        default=False,
        help_text="Valid medical certificate required"
    )
    
    # NOTE: Weather/wind constraints removed - these are operational decisions
    # for PIC and Duty Officer, not software enforcement
    
    # Administrative
    created_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = ['glider', 'qualification', 'requirement_type']
        ordering = ['glider', 'requirement_type']
    
    def __str__(self):
        return f"{self.glider} requires {self.qualification.code} for {self.get_requirement_type_display()}"
```

#### Enhanced Qualification Validation System

```python
class GliderAccessValidator:
    """
    Enforces qualification requirements for glider access.
    This completes the odontogenesis of the qualification badges.
    """
    
    @staticmethod
    def can_member_access_glider(member, glider, flight_type='solo'):
        """
        Check if member has required qualifications for glider access.
        Primary validation based on pilot rating status, not aircraft configuration.
        
        Args:
            member: Member instance
            glider: Glider instance
            flight_type: 'solo', 'dual', or 'pic'
            
        Returns:
            tuple: (is_authorized: bool, missing_requirements: list)
        """
        
        missing_requirements = []
        
        # STEP 1: Check pilot rating status (primary validation)
        is_rated_pilot = member.glider_rating in ['private', 'commercial']
        is_student_pilot = member.glider_rating == 'student'
        
        if not (is_rated_pilot or is_student_pilot):
            missing_requirements.append(f"Member rating '{member.glider_rating}' not recognized for flight operations")
            return False, missing_requirements
        
        # STEP 2: Get glider-specific requirements
        requirements = GliderQualificationRequirement.objects.filter(
            glider=glider,
            requirement_type__in=[flight_type, 'either']
        )
        
        if not requirements.exists():
            # No specific requirements - apply basic rating-based validation
            if is_student_pilot and flight_type == 'solo':
                missing_requirements.append("Student pilots require solo endorsement for solo flights")
                return False, missing_requirements
            return True, []
        
        # STEP 3: Validate specific glider qualifications
        for req in requirements:
            # Check if member has the required qualification
            member_qual = MemberQualification.objects.filter(
                member=member,
                qualification=req.qualification,
                is_qualified=True
            ).first()
            
            if not member_qual:
                missing_requirements.append(f"Missing {req.qualification.name}")
                continue
            
            # CRITICAL: Check if qualification is current (odontogenesis enforcement!)
            if member_qual.expiration_date and member_qual.expiration_date < timezone.now().date():
                missing_requirements.append(f"{req.qualification.name} expired on {member_qual.expiration_date}")
                continue
            
            # Check optional minimum hours requirements (if club enables this)
            # NOTE: Many clubs prefer not to enforce this due to external training
            if req.minimum_hours_total and hasattr(member, 'get_total_flight_hours'):
                try:
                    total_hours = member.get_total_flight_hours()
                    if total_hours < req.minimum_hours_total:
                        missing_requirements.append(f"Club policy: Need {req.minimum_hours_total} total hours (have {total_hours})")
                except:
                    # External training records not available - skip enforcement
                    pass
            
            if req.minimum_hours_type and hasattr(member, 'get_aircraft_type_hours'):
                try:
                    type_hours = member.get_aircraft_type_hours(glider.model)
                    if type_hours < req.minimum_hours_type:
                        missing_requirements.append(f"Club policy: Need {req.minimum_hours_type} hours in {glider.model} (have {type_hours})")
                except:
                    # External training records not available - skip enforcement
                    pass
        
        # STEP 4: Rating-specific additional validation
        if is_student_pilot:
            # Student pilots have additional restrictions
            if flight_type == 'solo' and glider.seats == 1:
                # Single-seater solo requires specific endorsement
                solo_endorsement = MemberQualification.objects.filter(
                    member=member,
                    qualification__code__icontains='solo',
                    is_qualified=True
                ).exists()
                if not solo_endorsement:
                    missing_requirements.append("Student pilot requires solo endorsement for single-seater aircraft")
        
        is_authorized = len(missing_requirements) == 0
        return is_authorized, missing_requirements
    
    @staticmethod
    def get_accessible_gliders(member, flight_type='solo', date=None):
        """
        Get list of gliders member is qualified to access.
        This is the FIRST step - filter options before presenting to user.
        """
        accessible_gliders = []
        
        for glider in Glider.objects.filter(is_active=True, club_owned=True):
            # Skip grounded aircraft entirely
            if glider.is_grounded:
                continue
                
            # Check if member is qualified for this aircraft
            is_authorized, _ = GliderAccessValidator.can_member_access_glider(
                member, glider, flight_type
            )
            if is_authorized:
                accessible_gliders.append({
                    'glider': glider,
                    'qualification_status': 'qualified',
                    'available_times': glider.get_available_times(date) if date else None
                })
        
        return accessible_gliders
    
    @staticmethod
    def get_user_friendly_aircraft_list(member, flight_type='solo', date=None):
        """
        Returns a clean list for UI display - only shows what user can actually book.
        No teasing with unavailable options!
        """
        accessible = GliderAccessValidator.get_accessible_gliders(member, flight_type, date)
        
        if not accessible:
            return {
                'aircraft': [],
                'message': f"No aircraft available for {flight_type} flights. Contact an instructor about additional qualifications.",
                'suggestions': [
                    "Complete required aircraft checkouts",
                    "Ensure qualifications are current",
                    "Check with CFI about training requirements"
                ]
            }
        
        return {
            'aircraft': accessible,
            'message': f"Available aircraft for {flight_type} flights:",
            'total_count': len(accessible)
        }
```

### Integration with Reservation System

#### Enhanced GliderReservation Validation

```python
# Update the GliderReservation.clean() method
def clean(self):
    """Enhanced validation with qualification enforcement"""
    from django.core.exceptions import ValidationError
    
    # Existing validations...
    
    # NEW: Enforce qualification requirements
    flight_type = 'solo' if self.reservation_type == 'solo' else 'dual'
    is_authorized, missing_requirements = GliderAccessValidator.can_member_access_glider(
        self.member, self.glider, flight_type
    )
    
    if not is_authorized:
        raise ValidationError(
            f"Member not qualified for {self.glider}: {', '.join(missing_requirements)}"
        )
```

### Database Migration Plan

#### Step 1: Create GliderQualificationRequirement Table
```sql
CREATE TABLE duty_roster_gliderqualificationrequirement (
    id BIGSERIAL PRIMARY KEY,
    glider_id BIGINT NOT NULL REFERENCES logsheet_glider(id),
    qualification_id BIGINT NOT NULL REFERENCES instructors_clubqualificationtype(id),
    requirement_type VARCHAR(15) NOT NULL DEFAULT 'either',
    minimum_hours_total DECIMAL(6,1) NULL,
    minimum_hours_type DECIMAL(6,1) NULL,
    requires_instructor_present BOOLEAN NOT NULL DEFAULT FALSE,
    requires_current_medical BOOLEAN NOT NULL DEFAULT FALSE,
    max_wind_speed INTEGER NULL,
    max_crosswind INTEGER NULL,
    created_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE(glider_id, qualification_id, requirement_type)
);
```

#### Step 2: Populate Initial Requirements
```python
# Example data population for common club aircraft
ASK_21_qual = ClubQualificationType.objects.get(code='ASK-21')
ASK_21_glider = Glider.objects.get(competition_number='ASK')

GliderQualificationRequirement.objects.create(
    glider=ASK_21_glider,
    qualification=ASK_21_qual,
    requirement_type='solo',
    minimum_hours_total=10.0,
    notes='Standard ASK-21 solo checkout required'
)
```

### Administrative Interface

#### Enhanced Admin for Glider Requirements
```python
@admin.register(GliderQualificationRequirement)
class GliderQualificationRequirementAdmin(admin.ModelAdmin):
    list_display = ('glider', 'qualification', 'requirement_type', 'minimum_hours_total')
    list_filter = ('requirement_type', 'glider__model', 'qualification__code')
    search_fields = ('glider__competition_number', 'qualification__name')
    autocomplete_fields = ('glider', 'qualification')
    
    fieldsets = (
        (None, {
            'fields': ('glider', 'qualification', 'requirement_type')
        }),
        ('Hour Requirements', {
            'fields': ('minimum_hours_total', 'minimum_hours_type')
        }),
        ('Safety Requirements', {
            'fields': ('requires_instructor_present', 'requires_current_medical')
        }),
        ('Notes', {
            'fields': ('notes',)
        })
    )
```

### User Interface Updates

#### Member Qualification Display
```html
<!-- Enhanced member qualification display with aircraft access -->
<div class="qualification-badge">
    <img src="{{ qual.icon.url }}" alt="{{ qual.name }}">
    <div class="qualification-details">
        <strong>{{ qual.name }}</strong>
        <div class="authorized-aircraft">
            <small class="text-muted">
                Authorizes: 
                {% for glider in qual.authorized_gliders.all %}
                    {{ glider.competition_number }}{% if not forloop.last %}, {% endif %}
                {% endfor %}
            </small>
        </div>
    </div>
</div>
```

#### Reservation Form Enhancement
```html
<!-- Glider selection with qualification indicators -->
<select name="glider" class="form-control">
  {% for glider in available_gliders %}
    <option value="{{ glider.id }}" 
            {% if not glider.user_qualified %}disabled{% endif %}>
      {{ glider }} 
      {% if not glider.user_qualified %} - QUALIFICATION REQUIRED{% endif %}
    </option>
  {% endfor %}
</select>
```

### Implementation Priority

1. **Phase 1**: Create `GliderQualificationRequirement` model and admin
2. **Phase 2**: Implement `GliderAccessValidator` validation logic
3. **Phase 3**: Integrate validation into reservation system
4. **Phase 4**: Update UI to show qualification status and requirements
5. **Phase 5**: Populate initial qualification requirements for existing aircraft

This odontogenic enhancement transforms the qualification badges from **cosmetic indicators** to **functional access controls**, ensuring that only properly qualified members can reserve and operate specific aircraft through systematic enforcement development.