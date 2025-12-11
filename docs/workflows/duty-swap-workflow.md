# Duty Swap Workflow - Issue #1

## Overview
This workflow handles the process where duty crew members (instructors, tow pilots, duty officers, assistant duty officers) need to find replacements for their scheduled duties when conflicts arise.

## User Story
Alice is the designated flight instructor scheduled for duty on Saturday, but she has a bar mitzvah to attend and can't make it. She needs to find a replacement. In the legacy system, all interactions happened via email. In the new system, the duty roster program handles all swaps through the web interface with no direct email interaction between instructors.

## Complete Workflow

```mermaid
graph TB
    Start[Alice: Instructor on Saturday] --> Conflict{Alice has<br/>conflict}
    Conflict -->|Yes| CalendarClick[Alice clicks Saturday<br/>on duty calendar]
    CalendarClick --> DayModal[Day detail modal opens]
    DayModal --> RequestButton[Alice clicks<br/>'Request Swap/Coverage']

    RequestButton --> RequestForm[Request Form]
    RequestForm --> FormFields{Fill form}

    FormFields --> Role[Role: Instructor<br/>pre-filled]
    FormFields --> Date[Date: Saturday<br/>pre-filled]
    FormFields --> RequestType{Request Type}
    FormFields --> Emergency[Emergency?<br/>Yes/No]
    FormFields --> Notes[Notes:<br/>'Bar mitzvah']

    RequestType -->|General| GeneralReq[Broadcast to all<br/>eligible instructors]
    RequestType -->|Direct| DirectReq[Direct to specific<br/>member Bob]
    RequestType -->|Cover Only| CoverReq[Just need coverage,<br/>no swap needed]

    GeneralReq --> EmailAll[Email sent to:<br/>Bob, Charlie, all instructors]
    DirectReq --> EmailBob[Email sent to:<br/>Bob only]
    CoverReq --> EmailAll

    EmailAll --> ViewRequest1[Bob receives email]
    EmailAll --> ViewRequest2[Charlie receives email]
    EmailBob --> ViewRequest1

    ViewRequest1 --> BobDecision{Bob's Action}
    ViewRequest2 --> CharlieDecision{Charlie's Action}

    BobDecision -->|Ignore| WaitMore[Request stays open]
    BobDecision -->|Make Offer| BobOffer[Bob creates offer]

    CharlieDecision -->|Ignore| WaitMore
    CharlieDecision -->|Make Offer| CharlieOffer[Charlie creates offer]

    BobOffer --> OfferType1{Bob's Offer Type}
    OfferType1 -->|Swap| BobSwapDate[Bob proposes:<br/>Next Saturday]
    OfferType1 -->|Cover| BobCover[Bob: I'll just take it<br/>no swap needed]

    CharlieOffer --> OfferType2{Charlie's Offer Type}
    OfferType2 -->|Swap| CharlieSwapDate[Charlie proposes:<br/>2 weeks Saturday]
    OfferType2 -->|Cover| CharlieCover[Charlie: I'll take it<br/>no swap needed]

    BobSwapDate --> OffersExist[Alice has 2 offers]
    BobCover --> OffersExist
    CharlieSwapDate --> OffersExist
    CharlieCover --> OffersExist

    OffersExist --> AliceNotified[Email to Alice:<br/>'You have offers!']
    AliceNotified --> AliceReview[Alice views<br/>'My Swap Requests']

    AliceReview --> AliceChoice{Alice's Decision}

    AliceChoice -->|Accept Bob| AcceptBob[Alice accepts Bob's offer]
    AliceChoice -->|Accept Charlie| AcceptCharlie[Alice accepts Charlie's offer]
    AliceChoice -->|Cancel Request| CancelRequest[Alice cancels request]
    AliceChoice -->|Wait| KeepOpen[Request stays open]

    AcceptBob --> BobOfferType{Bob's offer was}
    AcceptCharlie --> CharlieOfferType{Charlie's offer was}

    BobOfferType -->|Swap| SwapDuties1[System swaps:<br/>This Sat: Bob instructor<br/>Next Sat: Alice instructor]
    BobOfferType -->|Cover| CoverDuties1[System updates:<br/>This Sat: Bob instructor<br/>Alice: no swap needed]

    CharlieOfferType -->|Swap| SwapDuties2[System swaps:<br/>This Sat: Charlie instructor<br/>2wk Sat: Alice instructor]
    CharlieOfferType -->|Cover| CoverDuties2[System updates:<br/>This Sat: Charlie instructor<br/>Alice: no swap needed]

    SwapDuties1 --> MarkFulfilled[Mark request fulfilled]
    CoverDuties1 --> MarkFulfilled
    SwapDuties2 --> MarkFulfilled
    CoverDuties2 --> MarkFulfilled

    MarkFulfilled --> DeclineOthers[Auto-decline other offers]
    DeclineOthers --> NotifyBoth[Email confirmations to:<br/>Alice + Bob/Charlie]

    NotifyBoth --> UpdateCalendar[Update duty calendar<br/>visible to all members]
    UpdateCalendar --> Complete[✅ Swap Complete]

    CancelRequest --> NotifyOfferers[Email Bob & Charlie:<br/>'Alice cancelled request']
    NotifyOfferers --> ArchiveRequest[Archive cancelled request]
    ArchiveRequest --> End[End]

    KeepOpen --> TimeCheck{Time until duty}
    WaitMore --> TimeCheck

    TimeCheck -->|>48 hours| StayOpen[Request stays open<br/>normal priority]
    TimeCheck -->|24-48 hours| EscalateWarning[Send reminder email:<br/>'Still need coverage!']
    TimeCheck -->|<24 hours| EscalateEmergency[Auto-escalate to<br/>EMERGENCY status]

    EscalateEmergency --> NotifyDO[Email Duty Officer:<br/>'No coverage for Saturday']
    NotifyDO --> RoleCheck{What role<br/>is missing?}

    RoleCheck -->|Tow Pilot| MustCancel[CRITICAL: No tow pilot<br/>= No operations possible]
    RoleCheck -->|Duty Officer| MustCancel2[CRITICAL: No DO<br/>= No one in charge]
    RoleCheck -->|Instructor| OptionalCancel{Duty Officer<br/>Decision}
    RoleCheck -->|ADO| OptionalCancel

    MustCancel --> CancelOps[DO cancels operations<br/>for Saturday]
    MustCancel2 --> CancelOps

    DOAssigns --> MarkFulfilled
    OpsWithout --> NotifyMembers[Email members:<br/>'No [role] Saturday,<br/>ops still happening']
    NotifyMembers --> End
    CancelOps --> NotifyAll[Email all members:<br/>'Ops cancelled Saturday']
    NotifyAll --> End

    StayOpen --> MoreOffers{More offers<br/>come in?}
    MoreOffers -->|Yes| AliceNotified
    MoreOffers -->|No| TimeCheck

    EscalateWarning --> MoreOffers

    Complete --> End

    style Start fill:#e1f5ff
    style Complete fill:#c8e6c9
    style End fill:#ffcdd2
    style EscalateEmergency fill:#ff9800
    style CancelOps fill:#f44336
    style MarkFulfilled fill:#4caf50
    style NotifyDO fill:#ff5722
```

## Key Features

### 1. Request Types
- **General Broadcast**: Request sent to all eligible members for that role
- **Direct Request**: Request sent to a specific member only
- **Cover Only**: Someone just takes the duty, no swap needed

### 2. Offer Types
- **Swap**: Trade duties on two different dates
- **Cover**: Take the duty with no expectation of return

### 3. Time-based Escalation
- **Normal** (>48 hours): Request stays open, normal priority
- **Warning** (24-48 hours): Reminder email sent to eligible members
- **Emergency** (<24 hours): Auto-escalate, notify Duty Officer

### 4. Resolution Paths
- Requester accepts an offer → swap/cover completed
- Requester cancels request → all offerers notified
- No offers by deadline → Duty Officer decides based on role:
  - **Critical roles (Tow Pilot, Duty Officer)**: Operations MUST be cancelled
    - No tow pilot = can't fly
    - No duty officer = no one in charge
  - **Optional roles (Instructor, ADO)**: Operations can proceed without role, or DO can cancel, or DO can manually assign someone
- Request stays open until resolved or duty day arrives

### 5. Roles Covered
- Instructor
- Tow Pilot
- Duty Officer
- Assistant Duty Officer

## Email Notifications

### Request Created
**To:** All eligible members (or specific member if direct request)
**Content:**
- Who needs coverage (Alice)
- What role (Instructor)
- What date (Saturday)
- Why (bar mitzvah)
- Link to make an offer

### Offer Made
**To:** Requester (Alice)
**Content:**
- Who made offer (Bob)
- What type (swap for next Saturday, or cover)
- Link to review and accept/decline

### Offer Accepted
**To:** Both parties (Alice and Bob)
**Content:**
- Swap details confirmed
- Updated calendar dates
- Thank you message

### Offer Auto-declined
**To:** Declined offerer (Charlie)
**Content:**
- Alice accepted another offer
- Thank you for offering
- Encouragement to help with future requests

### Request Cancelled
**To:** All offerers
**Content:**
- Alice cancelled the request
- No longer needs help
- Thank you for offering

### Emergency Escalation
**To:** Duty Officer
**Content:**
- Critical: No coverage for [Role] on [Date]
- Requester: Alice
- Time remaining: <24 hours
- **If Tow Pilot or Duty Officer**: Operations MUST be cancelled (critical roles)
  - No tow pilot = can't fly
  - No duty officer = no one in charge
- **If Instructor/ADO**: Options available (proceed without role, find someone, or cancel)
- Link to duty assignment editor

### Operations Cancelled
**To:** All active members
**Content:**
- Operations cancelled for [Date]
- Reason: No [Role] coverage available
- **Critical roles**: Tow Pilot, Duty Officer (required for operations)
  - No tow pilot = can't fly
  - No duty officer = no one in charge
- **Optional roles**: Instructor, ADO (ops can proceed without, but better to have)
- Contact Duty Officer with questions

### Operations Proceeding Without Role
**To:** All active members
**Content:**
- Operations happening on [Date]
- Note: No [Role] available this day
- Example: "No instructor available Saturday - club gliders only, no instruction"
- Contact Duty Officer if you can help fill the role

## Open Questions

### Q1: Multiple Offers - Negotiation
Should Bob & Charlie be able to negotiate/comment on offers, or does Alice just pick one and others auto-decline?

### Q2: Cover Accounting
If Bob "covers" Alice with no swap expected, should we:
- Track it as a favor owed?
- Affect future roster fairness?
- Just update calendar with no accounting?

### Q3: Emergency Escalation - DO UI
When DO gets emergency notification, should they have UI to:
- Manually assign someone (requires their permission)?
- Or just email/call and manually update the calendar in admin?

## Technical Implementation Notes

### Existing Models (already in codebase)
- `DutySwapRequest`: Request for coverage/swap
- `DutySwapOffer`: Offer to help with a request
- `DutyAssignment`: The actual duty assignments

### New Components Needed
- Views for creating/managing requests
- Views for making/accepting offers
- Templates for all UIs
- Email templates for notifications
- URL routing
- Management command for time-based escalation (CronJob)
- Tests for complete workflow

### UI Access Points
- **Calendar day modal**: "Request Swap" button when viewing your own duty
- **Duty Roster navbar**: Link to "My Swap Requests" and "Open Requests"
- **Dashboard**: Alerts for pending offers/requests
