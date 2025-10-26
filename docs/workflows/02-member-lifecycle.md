# Member Lifecycle Workflow

## Manager Overview

The member lifecycle describes how individuals join the club, get their profiles set up, receive appropriate permissions, and progress through different membership levels. This is the foundation workflow that enables all other club activities.

**Key Stages:**
1. **Registration** - New user creates account via Google OAuth2
2. **Profile Setup** - Basic information and club-specific details
3. **Membership Activation** - Admin approval and status assignment
4. **Role Assignment** - Permissions based on qualifications and club roles
5. **Ongoing Management** - Updates, renewals, and status changes

## Process Flow

```mermaid
flowchart TD
    A[New User Visits Site] --> B{Has Google Account?}
    B -->|No| C[Create Google Account]
    B -->|Yes| D[Click Login]
    C --> D
    
    D --> E[Google OAuth2 Flow]
    E --> F[Django Social Auth Pipeline]
    F --> G[Create Member Record]
    G --> H[Set Default Status: 'Guest']
    
    H --> I[User Completes Profile]
    I --> J[Upload Photo]
    I --> K[Add Bio/Contact Info]
    I --> L[Profile Review Complete]
    
    L --> M{Admin Review}
    M -->|Approved| N[Set Membership Status]
    M -->|Needs More Info| O[Request Additional Info]
    M -->|Rejected| P[Set Inactive Status]
    
    N --> Q[Assign Initial Roles]
    Q --> R[Send Welcome Notification]
    R --> S[Member Active]
    
    O --> I
    P --> T[Account Suspended]
    
    S --> U[Ongoing Profile Updates]
    U --> V[Role Changes]
    U --> W[Badge Awards]
    U --> X[Status Updates]
    
    style A fill:#e1f5fe
    style S fill:#e8f5e8
    style T fill:#ffebee
```

## Technical Implementation

### **Models Involved**
- **`members.Member`**: Extended Django User model with club-specific fields
- **`members.Badge`**: Soaring badges and certifications
- **`notifications.Notification`**: Welcome messages and status updates

### **Key Files**
- **Pipeline**: `members/pipeline.py` - OAuth2 user creation and setup
- **Views**: `members/views.py` - Profile management and display
- **Forms**: `members/forms.py` - Profile editing and validation
- **Admin**: `members/admin.py` - Membership approval and management

### **Authentication Flow Details**

```mermaid
sequenceDiagram
    participant User as New User
    participant Google as Google OAuth2
    participant Django as Django App
    participant Pipeline as Social Auth Pipeline
    participant DB as Database
    participant Admin as Club Admin
    
    User->>Google: Initiate Login
    Google->>User: Request Permissions
    User->>Google: Grant Permissions
    Google->>Django: Return Auth Code
    Django->>Pipeline: Process User Data
    
    Pipeline->>Pipeline: debug_pipeline_data()
    Pipeline->>Pipeline: create_username()
    Pipeline->>Pipeline: set_default_membership_status()
    Pipeline->>Pipeline: fetch_google_profile_picture()
    
    Pipeline->>DB: Create Member Record
    DB->>Django: Return Member Instance
    Django->>User: Redirect to Profile
    
    User->>Django: Complete Profile
    Django->>Admin: Notify of New Member
    Admin->>Django: Review and Approve
    Django->>User: Send Welcome Notification
```

### **Member Status Progression**

```mermaid
stateDiagram-v2
    [*] --> Guest: OAuth2 Registration
    Guest --> Applicant: Profile Completed
    Applicant --> Full_Member: Admin Approval
    Applicant --> Inactive: Application Rejected
    
    Full_Member --> Student_Member: Learning to Fly
    Student_Member --> Full_Member: Solo/License
    Full_Member --> Family_Member: Family Plan
    Full_Member --> Service_Member: Military Status
    Full_Member --> Honorary_Member: Special Recognition
    Full_Member --> Emeritus_Member: Retirement
    
    Full_Member --> Inactive: Non-payment/Violation
    Student_Member --> Inactive: Non-payment/Violation
    Inactive --> Full_Member: Reinstatement
    
    note right of Full_Member
        Default active status
        Can fly, instruct, serve duty
    end note
    
    note right of Inactive
        No system access
        Cannot participate
    end note
```

### **Database Schema**

```mermaid
erDiagram    
    Member {
        int id PK
        string username UK
        string email UK
        string first_name
        string last_name
        string nickname
        string membership_status
        boolean is_active
        boolean webmaster
        boolean instructor
        boolean duty_officer
        boolean tow_pilot
        text bio
        image profile_picture
        date date_joined
        date last_login
    }
    
    Badge {
        int id PK
        string name
        string description
        image badge_image
        int sequence
    }
    
    MemberBadge {
        int id PK
        int member_id FK
        int badge_id FK
        date date_earned
        string certificate_number
    }
    
    Member ||--o{ MemberBadge : earns
    Badge ||--o{ MemberBadge : awarded
```

## Key Integration Points

### **Downstream Dependencies**
Once a member is active, they can participate in:
- **Duty Roster**: Assignment to duty officer, instructor, or tow pilot roles
- **Flight Operations**: Logging flights as pilot or passenger
- **Instruction**: Taking lessons or providing instruction
- **Knowledge Tests**: Taking written examinations
- **Notifications**: Receiving club communications

### **Permission-Based Access**
Member roles determine access to different parts of the system:

```mermaid
flowchart LR
    Member[Active Member] --> A{Role Check}
    A -->|webmaster=True| B[Full Admin Access]
    A -->|instructor=True| C[Training Management]
    A -->|duty_officer=True| D[Logsheet Management]
    A -->|tow_pilot=True| E[Tow Operations]
    A -->|Default| F[Basic Member Access]
    
    B --> G[Site Configuration]
    B --> H[User Management]
    B --> I[All Data Access]
    
    C --> J[Lesson Planning]
    C --> K[Student Progress]
    C --> L[Training Records]
    
    D --> M[Flight Logging]
    D --> N[Logsheet Closeout]
    D --> O[Maintenance Reports]
    
    E --> P[Tow Logging]
    E --> Q[Tow Rate Management]
    
    F --> R[Profile Management]
    F --> S[Flight History]
    F --> T[Badge Progress]
```

## Common Workflows

### **New Member Onboarding Checklist**

```mermaid
flowchart TD
    A[OAuth2 Registration] --> B[Profile Photo Upload]
    B --> C[Bio Completion]
    C --> D[Contact Information]
    D --> E[Emergency Contact]
    E --> F[Admin Review]
    
    F --> G{Approval Status}
    G -->|Approved| H[Welcome Email]
    G -->|Rejected| I[Rejection Notice]
    G -->|Needs Info| J[Request Details]
    
    H --> K[Membership Card Generated]
    K --> L[Role Assignment]
    L --> M[Training Assessment]
    M --> N[Duty Roster Eligible]
    
    J --> C
    I --> O[Account Suspended]
    
    style A fill:#e1f5fe
    style N fill:#e8f5e8
    style O fill:#ffebee
```

### **Member Status Changes**

```mermaid
flowchart LR
    A[Status Change Request] --> B{Change Type}
    B -->|Promotion| C[Admin Approval Required]
    B -->|Demotion| D[Admin Action Only]
    B -->|Role Addition| E[Qualification Check]
    B -->|Role Removal| F[Admin Confirmation]
    
    C --> G[Update Database]
    D --> G
    E --> H{Meets Requirements?}
    F --> G
    
    H -->|Yes| G
    H -->|No| I[Deny Request]
    
    G --> J[Send Notification]
    G --> K[Update Permissions]
    G --> L[Log Change]
    
    I --> M[Explain Requirements]
```

## Known Gaps & Improvements 

### **Current Strengths**
- ✅ Seamless Google OAuth2 integration
- ✅ Comprehensive profile management
- ✅ Flexible role-based permissions
- ✅ Automated welcome process
- ✅ Badge tracking and display

### **Identified Gaps**
- 🟡 **Membership Renewals**: No automated renewal process or expiration tracking
- 🟡 **Family Plans**: Limited support for family membership management
- 🟡 **Payment Integration**: No payment processing for membership dues
- 🟡 **Document Management**: No member document storage (certificates, medical, etc.)
- 🟡 **Communication Preferences**: Limited notification preference management

### **Improvement Opportunities**
- 🔄 **Self-Service Role Requests**: Allow members to request role changes with approval workflow
- 🔄 **Onboarding Automation**: Guided setup process for new members
- 🔄 **Profile Completeness**: Progress indicators and reminders for incomplete profiles
- 🔄 **Bulk Operations**: Admin tools for bulk member updates and communications
- 🔄 **Integration APIs**: Connect with external membership management systems

### **Data Quality Issues**
- 🔄 **Duplicate Detection**: Prevent duplicate accounts for same person
- 🔄 **Profile Validation**: Ensure required fields are completed
- 🔄 **Contact Updates**: Automated reminders to keep contact information current
- 🔄 **Photo Standards**: Guidelines and validation for profile photos

## Related Workflows

- **[Duty Roster Workflow](05-duty-roster-workflow.md)**: How members get assigned to duties
- **[Instruction Workflow](03-instruction-workflow.md)**: How members progress through training
- **[Knowledge Test Lifecycle](09-knowledge-test-lifecycle.md)**: How members take written exams
- **[System Overview](01-system-overview.md)**: How member management fits into the broader system

---

*The member lifecycle is the foundation that enables all other club activities. A well-managed member database ensures smooth operations across all other workflows.*