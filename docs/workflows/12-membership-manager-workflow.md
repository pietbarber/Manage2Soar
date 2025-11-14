# Membership Manager Workflow

## Manager Overview

The Membership Manager is one of the most critical human roles in the soaring club, serving as the primary gateway for new member onboarding and ongoing membership administration. With the implementation of the visitor contact system (Issue #70), Membership Managers now have streamlined tools to handle inquiries, process applications, and manage member lifecycles efficiently.

**Core Responsibilities:**
- **Visitor Contact Management**: Process and respond to inquiries from the `/contact/` form
- **New Member Onboarding**: Review applications, verify profiles, approve/reject memberships
- **Membership Status Management**: Handle renewals, status changes, and member transitions
- **Waiting List Administration**: Manage prospective member queue and communications
- **Communication Coordination**: Send welcome emails, notifications, and updates

**Key Integration Points:**
- Visitor contact form system (`cms.models.VisitorContact`)
- Member management through Django admin (`members.models.Member`)
- Email notification system (`notifications.models.Notification`)
- OAuth2 authentication pipeline for new registrations

## Process Flow

### High-Level Membership Manager Workflow

```mermaid
flowchart TD
    A[Daily Responsibilities] --> B[Check Visitor Contacts]
    A --> C[Review New OAuth2 Registrations]
    A --> D[Process Membership Applications]
    A --> E[Manage Waiting List]

    B --> B1[Visitor Contact Triage]
    B1 --> B2{Contact Type}
    B2 -->|Trial Flight| B3[Forward to CFI]
    B2 -->|Membership Info| B4[Send Info Package]
    B2 -->|Technical Questions| B5[Forward to Webmaster Group]
    B2 -->|General Questions| B6[Direct Response]
    B4 --> B7[Add to Waiting List if Interested]

    C --> C1[OAuth2 User Assessment]
    C1 --> C2{User Type}
    C2 -->|Legitimate Interest| C3[Welcome & Invitation to Apply]
    C2 -->|Unwelcome/Spam| C4[DELETE Account]
    C2 -->|Returning Member| C5[Status Review]
    C3 --> C6{Waiting List Status?}
    C6 -->|Full Capacity| C7[Inform of Waiting List]
    C6 -->|Space Available| C8[Direct Application Invitation]
    C7 --> C9[Provide Application Option]
    C8 --> C10[Application Form Completion]
    C9 --> C10
    C10 --> C11{Profile Complete?}
    C11 -->|No| C12[Request Additional Info]
    C11 -->|Yes| C13[Begin Approval Process]
    C12 --> C11
    C13 --> C14[Background Verification]
    C14 --> C15{Approve?}
    C15 -->|Yes| C16[Activate Membership]
    C15 -->|No| C17[Send Rejection Notice]

    D --> D1[Application Review]
    D1 --> D2[Reference Checks]
    D2 --> D3[Club Integration Assessment]
    D3 --> D4[Final Approval Decision]

    E --> E1[Contact Waiting List Members]
    E1 --> E2[Update Priority Status]
    E2 --> E3[Process New Openings]

    C16 --> F[Send Welcome Package]
    F --> G[Schedule Orientation]
    G --> H[Monitor Integration]

    style A fill:#e1f5fe
    style F fill:#e8f5e8
    style C16 fill:#e8f5e8
    style C4 fill:#ffcdd2
```

## Detailed Workflows

### 1. Visitor Contact Response Workflow

**Purpose**: Process and respond to inquiries submitted through the club's `/contact/` form.

**Access Method**: Django Admin → CMS → Visitor Contacts

```mermaid
sequenceDiagram
    participant V as Visitor
    participant CF as Contact Form
    participant MM as Membership Manager
    participant N as Notification System
    participant CFI as Chief Flight Instructor

    V->>CF: Submit contact inquiry
    CF->>MM: Email notification sent
    CF->>N: System notification created

    MM->>MM: Review inquiry details
    MM->>MM: Determine inquiry type

    alt Trial Flight Request
        MM->>CFI: Forward to flight operations
        CFI->>V: Schedule trial flight
    else Membership Information
        MM->>MM: Prepare information package
        MM->>V: Send membership details
        MM->>MM: Add to waiting list if interested
    else General Questions
        MM->>V: Direct response
    end

    MM->>CF: Update contact status in admin
```

**Response Time Standards:**
- **Trial Flight Requests**: Within 24 hours on weekdays
- **Membership Inquiries**: Within 2-3 business days
- **General Questions**: Within 1 week

**Contact Triage Categories:**

| Category | Description | Response Protocol |
|----------|-------------|-------------------|
| **Trial Flights** | First-time visitors interested in flying | Forward to CFI, provide scheduling info |
| **Membership Applications** | Serious about joining the club | Send application package, inform of waiting list status |
| **Technical Questions** | Website issues, system problems, IT support | Forward to webmaster group |
| **General Information** | Questions about club activities | Direct response with club information |
| **Aircraft/Equipment** | Questions about fleet and maintenance | Forward to maintenance officer |
| **Events/Activities** | Club events and competitions | Forward to appropriate organizer |

### 2. New Member Application Process

**Purpose**: Process membership applications from multiple sources and handle various registration scenarios.

```mermaid
flowchart TD
    %% Multiple Entry Points
    A1[OAuth2 Registration] --> A2{User Assessment}
    A2 -->|Unknown User| A3[Welcome Email Process]
    A2 -->|Unwelcome/Spam| A4[DELETE Account]
    A2 -->|Returning Member| A5[Status Review]

    B1[Visitor Contact Form] --> B2[Information Package]
    B2 --> B3[Application Invitation]

    C1[Direct Application] --> C2[Manual Entry Process]
    C2 --> C3[Create User Account]

    D1[Referral/Recommendation] --> D2[Contact & Invite]
    D2 --> D3[Expedited Review]

    %% Common Application Flow
    A3 --> E[Explain Membership Process]
    B3 --> E
    C3 --> E
    D3 --> E

    E --> F{Club at Capacity?}
    F -->|Yes| G[Explain Waiting List]
    F -->|No| H[Direct Application Path]
    G --> I[Offer Wait List Application]
    H --> J[Provide Application Form]
    I --> J

    J --> K[User Completes Application]
    K --> L{Profile Complete?}
    L -->|No| M[Request Missing Information]
    M --> N[Follow-up Communication]
    N --> L
    L -->|Yes| O[Background Verification]

    O --> P[Reference Checks]
    O --> Q[Experience Verification]
    O --> R[Club Fit Assessment]

    P --> S[Final Review Meeting]
    Q --> S
    R --> S

    S --> T{Approval Decision}
    T -->|Approved| U[Set Initial Status]
    T -->|Conditional| V[Set Probationary Status]
    T -->|Rejected| W[Send Rejection Notice]

    U --> X[Send Welcome Package]
    V --> Y[Monitor Progress]
    X --> Z[Schedule Orientation]

    %% Deletion Path
    A4 --> A6[Document Reason]
    A6 --> A7[Remove All Data]

    style U fill:#e8f5e8
    style W fill:#ffebee
    style V fill:#fff3e0
    style A4 fill:#ffcdd2
    style A7 fill:#ffcdd2
```

#### Multiple Pathways to Membership

**1. OAuth2 Registration (Most Common)**
- Unknown users register via Google/OAuth2
- Membership Manager receives notification
- Assessment required: legitimate interest vs. unwelcome registration
- **DELETE Option**: For spam, inappropriate users, or obvious bad actors

**2. Visitor Contact Form**
- Prospective members inquire via `/contact/` form
- Information package sent with application invitation
- Often higher conversion rate due to demonstrated interest

**3. Direct Application**
- Walk-ins, phone calls, or in-person meetings
- Membership Manager manually creates user account if needed
- Direct entry into application process

**4. Referrals and Recommendations**
- Current members refer friends/family
- May warrant expedited review process
- Strong recommendation can influence approval

#### Handling Unwelcome Registrations

**Assessment Criteria:**
- Profile completeness and authenticity
- Email domain (spam indicators)
- Behavioral red flags in initial communications
- Previous negative history with club

**Deletion Process:**
1. Document reason for deletion
2. Remove user account and all associated data
3. Block email/domain if necessary
4. Report to other club managers if safety concern

**Application Review Checklist:**

#### Profile Completeness
- [ ] Full name and contact information
- [ ] Profile photo uploaded
- [ ] Biography/background completed
- [ ] Emergency contact information
- [ ] Aviation experience documented
- [ ] References provided (minimum 2)

#### Background Verification
- [ ] Previous club memberships verified
- [ ] Aviation credentials checked (if applicable)
- [ ] References contacted and verified
- [ ] No significant safety concerns identified
- [ ] Financial capability assessment (if required)

#### Club Integration Assessment
- [ ] Alignment with club values and culture
- [ ] Willingness to participate in club duties
- [ ] Availability for club activities
- [ ] Geographic proximity to club operations

### 3. Membership Status Management

**Purpose**: Handle ongoing membership administration including renewals, status changes, and transitions.

**Status Transitions (Club-Configurable):**

> **Note**: Each club may implement different membership progressions. The system supports flexible status management to accommodate various club structures. The example below shows Skyline Soaring Club's progression model.

**Skyline Soaring Club Model:**
```mermaid
stateDiagram-v2
    [*] --> Guest
    Guest --> PendingApproval : Application Submitted
    PendingApproval --> IntroductoryMember : Initial Approval
    PendingApproval --> Rejected : Not Approved

    IntroductoryMember --> ProbationaryMember : Orientation Complete
    ProbationaryMember --> FullMember : Probation Successful
    ProbationaryMember --> Inactive : Probation Failed

    Guest --> StudentMember : Academic Student Status
    StudentMember --> FullMember : Graduation/Age Change
    StudentMember --> Inactive : No Longer Student

    FullMember --> Inactive : Non-renewal/Issues
    Inactive --> FullMember : Reactivation
    Inactive --> [*] : Permanent Departure

    FullMember --> HonoraryMember : Special Recognition
    FullMember --> EmeritusMember : Retirement Status
```

**Status Definitions (Skyline Soaring Club):**
- **Guest**: Temporary access, trial flights only
- **Pending Approval**: Application under review
- **Introductory Member**: Newly approved, completing orientation
- **Probationary Member**: Full privileges under observation period
- **Student Member**: Reserved for high school/university students (not student pilots)
- **Full Member**: Standard active membership with all privileges
- **Honorary Member**: Special recognition status
- **Emeritus Member**: Retired member with limited privileges
- **Inactive**: Suspended or lapsed membership**Annual Renewal Process:**
1. **Pre-Renewal Communication** (60 days before expiration)
   - Send renewal notices via email
   - Include dues information and deadlines
   - Provide online renewal options

2. **Renewal Processing** (30-day window)
   - Track payments and confirmations
   - Update membership records
   - Handle special circumstances

3. **Post-Renewal Follow-up** (After deadline)
   - Contact non-renewals for status clarification
   - Process late renewals with appropriate penalties
   - Update member status to inactive if necessary

### 4. Waiting List Administration

**Purpose**: Manage the queue of prospective members when club membership is at capacity.

**Waiting List Management Process:**

```mermaid
flowchart TD
    A[New Inquiry] --> B{Membership Available?}
    B -->|Yes| C[Direct to Application Process]
    B -->|No| D[Add to Waiting List]

    D --> E[Assign Priority Number]
    E --> F[Send Waiting List Confirmation]
    F --> G[Regular Status Updates]

    H[Member Departure] --> I[Opening Available]
    I --> J[Contact Next on List]
    J --> K{Still Interested?}
    K -->|Yes| L[Begin Application Process]
    K -->|No| M[Remove from List]
    M --> N[Contact Next Person]

    G --> O[Quarterly Check-ins]
    O --> P{Maintain Interest?}
    P -->|Yes| G
    P -->|No| Q[Remove from List]

    style C fill:#e8f5e8
    style L fill:#e8f5e8
```

**Waiting List Priority Factors:**
1. **Date of Initial Contact** (primary factor)
2. **Completion of Requirements** (application materials submitted)
3. **Geographic Proximity** (local vs. distant members)
4. **Aviation Experience** (certificated pilots may get priority)
5. **Special Skills** (mechanics, instructors, etc.)
6. **Referrals** (existing member recommendations)

## Technical Implementation

### Django Admin Configuration

**Visitor Contact Management:**
```python
# cms/admin.py - VisitorContactAdmin configuration
- List display: name, email, subject, submitted_at, handled_by
- List filters: submitted_at, handled
- Search fields: name, email, subject
- Bulk actions: mark_as_handled, export_to_csv
```

**Member Management Tools:**
```python
# members/admin.py - MemberAdmin configuration
- List display: username, full_name, membership_status, is_active
- List filters: membership_status, date_joined, is_active
- Search fields: username, first_name, last_name, email
- Bulk actions: activate_members, send_renewal_notices
```

### Key Model Relationships

```mermaid
erDiagram
    Member ||--o{ VisitorContact : "handles"
    Member ||--o{ Notification : "receives"
    Member }o--|| MembershipStatus : "has"
    Member ||--o{ Biography : "has"
    Member ||--|| Group : "member_of"

    VisitorContact {
        string name
        string email
        string subject
        text message
        datetime submitted_at
        boolean handled
        Member handled_by
    }

    Member {
        string username
        string email
        string membership_status
        boolean member_manager
        boolean is_active
        datetime date_joined
    }
```

### Integration Points

**Email Notification System:**
- Automatic notifications for new visitor contacts
- Welcome email templates for new members
- Renewal reminder scheduling
- Status change notifications

**Authentication Pipeline:**
- OAuth2 registration handling
- Unknown user flagging for review
- Automatic profile creation
- Permission assignment

## Standard Operating Procedures

### Communication Templates

#### Welcome Email Template
```
Subject: Welcome to [Club Name] - Next Steps

Dear [Member Name],

Congratulations! Your membership application has been approved, and we're excited to welcome you to [Club Name].

Your membership details:
- Status: [Membership Type]
- Member ID: [Member Number]
- Effective Date: [Start Date]

Next steps:
1. Complete your safety orientation (scheduled for [Date])
2. Review club operations manual
3. Set up your duty roster preferences
4. Join our member communication channels

Your membership manager: [Manager Name] ([Manager Email])

Welcome aboard!

[Club Leadership]
```

#### Rejection Notice Template
```
Subject: [Club Name] Membership Application Update

Dear [Applicant Name],

Thank you for your interest in joining [Club Name]. After careful review of your application, we regret to inform you that we cannot offer membership at this time.

[Specific reason - if appropriate to share]

We encourage you to:
- Address the noted concerns and reapply in [timeframe]
- Consider visiting as a guest to better understand our club culture
- Contact us if you have questions about this decision

We appreciate your understanding and wish you the best in your soaring endeavors.

Sincerely,
[Membership Manager Name]
```

### Response Time Standards

| Task Type | Target Response Time | Escalation Threshold |
|-----------|---------------------|---------------------|
| Visitor Contact - Trial Flight | 24 hours | 48 hours |
| Visitor Contact - General | 3 business days | 1 week |
| Application Review | 2 weeks | 3 weeks |
| Status Change Requests | 1 week | 2 weeks |
| Renewal Processing | Same day | 3 days |

### Documentation Requirements

**For Each New Member:**
- [ ] Completed application with all required fields
- [ ] Reference verification records
- [ ] Background check documentation (if required)
- [ ] Welcome package delivery confirmation
- [ ] Orientation completion record

**For Status Changes:**
- [ ] Reason for change documented
- [ ] Member notification sent and acknowledged
- [ ] System records updated
- [ ] Follow-up requirements noted

### Seasonal Considerations

**Flying Season (April - October):**
- Increased visitor contact volume
- Priority processing for trial flight requests
- Enhanced new member orientation scheduling
- Active waiting list management

**Off-Season (November - March):**
- Focus on administrative tasks
- Annual renewal processing
- Waiting list maintenance and updates
- Planning for next season's growth

## Club Capacity Management

### Capacity Assessment
The Membership Manager should regularly assess club capacity based on:
- **Facility Resources**: Hangar space, meeting room capacity
- **Equipment Availability**: Aircraft fleet utilization
- **Instructor Bandwidth**: Training capacity for new members
- **Safety Considerations**: Maintaining manageable group sizes

### Waiting List Management
When club approaches or reaches capacity:

1. **Transparent Communication**: Clearly explain capacity limitations
2. **Regular Updates**: Keep waiting list members informed of status
3. **Fair Processing**: First-come, first-served unless special circumstances
4. **Engagement Maintenance**: Invite to public events to maintain interest
5. **Capacity Monitoring**: Regular review of member activity levels

### Capacity Decision Framework
- **Hard Limits**: Insurance/regulatory requirements (non-negotiable)
- **Soft Limits**: Quality of experience considerations (flexible)
- **Seasonal Adjustments**: Consider weather impacts on activity levels
- **Growth Planning**: Balance current capacity with future expansion

## Quality Assurance and Metrics

### Key Performance Indicators

**Response Metrics:**
- Average response time to visitor contacts
- Application processing time (goal: <2 weeks)
- Member satisfaction with onboarding process
- Waiting list conversion rate

**Membership Health:**
- New member retention rate (1-year mark)
- Annual renewal rate
- Member engagement level
- Inactive member reactivation success

### Regular Reviews

**Monthly:**
- Visitor contact response time analysis
- Application pipeline review
- Waiting list status update
- Member status change tracking

**Quarterly:**
- New member integration success assessment
- Process improvement identification
- Communication template effectiveness review
- Waiting list priority adjustment

**Annually:**
- Complete membership workflow audit
- Renewal process optimization
- Member satisfaction survey
- Growth planning and capacity assessment

## Related Issues and References

- **Issue #70**: Visitor contact form implementation
- **Issue #24**: Waiting list tracking system
- **Issue #164**: Unknown user OAuth2 handling
- **Issue #180**: Workflow documentation project

**See Also:**
- [Member Lifecycle Workflow](02-member-lifecycle.md) - Technical member management
- [System Overview](01-system-overview.md) - Overall architecture
- [Security Workflow](10-security-workflow.md) - User permission management

---

*This workflow document addresses Issue #188 and provides comprehensive guidance for Membership Manager responsibilities and procedures.*
