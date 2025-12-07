# Instruction Workflow

## Manager Overview

The instruction workflow manages the complete training lifecycle for club members learning to fly gliders. This includes lesson planning, flight instruction, progress tracking, and certification management. The system integrates instruction records with flight logging to provide comprehensive training documentation.

**Key Stages:**
1. **Student Assessment** - Evaluate student readiness and goals
2. **Lesson Planning** - Create structured training curriculum
3. **Flight Instruction** - Conduct actual training flights
4. **Progress Tracking** - Monitor student advancement through syllabus
5. **Certification** - Document achievements and endorsements

## Process Flow

```mermaid
flowchart TD
    A[New Student Inquiry] --> B[Initial Assessment]
    B --> C[Training Plan Creation]
    C --> D[Syllabus Assignment]
    D --> E[Lesson Scheduling]

    E --> F[Pre-Flight Briefing]
    F --> G[Training Flight]
    G --> H[Post-Flight Debrief]
    H --> I[Lesson Documentation]

    I --> J{Student Progress Check}
    J -->|Needs More Practice| K[Schedule Additional Lessons]
    J -->|Ready for Next Phase| L[Advance to Next Lesson]
    J -->|Assessment Required| M[Schedule Check Flight]

    K --> E
    L --> N[Update Training Record]
    M --> O[Instructor Evaluation]

    N --> P{Phase Complete?}
    P -->|No| E
    P -->|Yes| Q[Phase Sign-off]

    O --> R{Check Flight Result}
    R -->|Pass| Q
    R -->|Needs Improvement| S[Remedial Training Plan]

    Q --> T{Training Complete?}
    T -->|No| U[Next Training Phase]
    T -->|Yes| V[Final Certification]

    S --> E
    U --> D
    V --> W[License Endorsement]
    W --> X[Training Complete]

    style A fill:#e1f5fe
    style X fill:#e8f5e8
    style S fill:#fff3e0
```

## Technical Implementation

### **Models Involved**
- **`instructors.TrainingLesson`**: Individual lesson records
- **`instructors.SyllabusDocument`**: Training curriculum structure
- **`instructors.TrainingPhase`**: Organized training stages
- **`instructors.ClubQualificationType`**: Certification types
- **`logsheet.Flight`**: Flight records linked to training
- **`members.Member`**: Students and instructors

### **Key Files**
- **Models**: `instructors/models.py` - Training data structures
- **Views**: `instructors/views.py` - Lesson management interface
- **Forms**: `instructors/forms.py` - Lesson creation and editing
- **Utils**: `instructors/utils.py` - Training logic and calculations
- **Signals**: `instructors/signals.py` - Automated notifications

### **Training Lesson Lifecycle**

```mermaid
sequenceDiagram
    participant Student as Student
    participant Instructor as Instructor
    participant System as Manage2Soar
    participant DO as Duty Officer
    participant Admin as Training Admin
    participant Email as Email System

    Student->>System: Request Training
    System->>Instructor: Notify of Student Request
    Instructor->>System: Create Lesson Plan

    System->>Student: Send Lesson Schedule
    System->>DO: Include in Flight Operations

    Instructor->>System: Conduct Pre-Flight Brief
    DO->>System: Log Training Flight
    Instructor->>System: Complete Instruction Report

    System->>System: Link Flight to Lesson
    System->>System: Update Progress Tracking
    System->>System: Track New Qualifications

    alt Instruction Report Submitted
        System->>Email: Send Report to Student
        Email->>Student: Email with lesson scores, notes, qualifications
        System->>Email: CC Instructors (if mailing list configured)
        Email->>Instructor: Copy of instruction report
        System->>Student: In-app notification
    end

    alt Lesson Complete
        System->>Admin: Update Training Records
    else More Practice Needed
        System->>Instructor: Schedule Follow-up
    end

    System->>System: Generate Training Reports
```

### **Training Progress Tracking**

```mermaid
stateDiagram-v2
    [*] --> Assessment: Student Enrollment
    Assessment --> PreSolo: Training Plan Approved

    state PreSolo {
        [*] --> BasicControls
        BasicControls --> Turns
        Turns --> SpoilerUse
        SpoilerUse --> PatternWork
        PatternWork --> LandingPractice
        LandingPractice --> [*]
    }

    PreSolo --> SoloPrep: Phase 1 Complete
    SoloPrep --> FirstSolo: Instructor Sign-off
    FirstSolo --> PostSolo: Solo Achievement

    state PostSolo {
        [*] --> CrossCountry
        CrossCountry --> AdvancedManeuvers
        AdvancedManeuvers --> WeatherDecision
        WeatherDecision --> [*]
    }

    PostSolo --> CheckRide: Phase 2 Complete
    CheckRide --> Certified: Examiner Approval
    CheckRide --> Remedial: Additional Training Needed
    Remedial --> PostSolo: Weakness Addressed

    Certified --> [*]: License Issued

    note right of FirstSolo
        Major milestone
        Insurance requirements
        Weather minimums
    end note
```

### **Database Schema**

```mermaid
erDiagram
    Member {
        int id PK
        string name
        boolean instructor
        string membership_status
    }

    TrainingPhase {
        int id PK
        string name
        text description
        int sequence_order
        boolean is_solo_phase
    }

    SyllabusDocument {
        int id PK
        string title
        text content
        int phase_id FK
        int lesson_number
        boolean required
    }

    TrainingLesson {
        int id PK
        int student_id FK
        int instructor_id FK
        int phase_id FK
        int syllabus_document_id FK
        date lesson_date
        time duration
        text pre_flight_notes
        text post_flight_notes
        string lesson_status
        decimal grade_score
        boolean phase_complete
    }

    Flight {
        int id PK
        int training_lesson_id FK
        int pilot_id FK
        int instructor_id FK
        datetime flight_start
        datetime flight_end
        string flight_type
    }

    ClubQualificationType {
        int id PK
        string name
        text requirements
        boolean requires_checkride
    }

    Member ||--o{ TrainingLesson : student
    Member ||--o{ TrainingLesson : instructor
    TrainingPhase ||--o{ SyllabusDocument : contains
    TrainingPhase ||--o{ TrainingLesson : part_of
    SyllabusDocument ||--o{ TrainingLesson : follows
    TrainingLesson ||--o{ Flight : documented_by
    ClubQualificationType ||--o{ Member : certified_in
```

## Key Integration Points

### **Flight Operations Integration**
Training lessons are tightly integrated with flight logging:

```mermaid
flowchart LR
    A[Training Lesson Created] --> B[Flight Scheduled]
    B --> C[Duty Officer Logs Flight]
    C --> D[Flight Linked to Lesson]
    D --> E[Instructor Completes Lesson]
    E --> F[Progress Updated]
    F --> G[Reports Generated]

    subgraph "Automatic Connections"
        H[Student → Pilot]
        I[Instructor → Instructor]
        J[Lesson Date → Flight Date]
        K[Training Type → Flight Purpose]
    end
```

### **Notification Triggers**

The system sends automated notifications for:

**In-App Notifications:**
- InstructionReport created/updated → Student notification with link to instruction record
- GroundInstruction logged → Student notification with instructor/date details
- MemberQualification awarded → Member notification with qualification details
- MemberBadge awarded → Member notification with link to badge board

**Email Notifications (Issue #366):**
- **Instruction Report Submission** → Email sent to student with full report details
  - **TO**: Student's email address
  - **CC**: Instructors mailing list (if configured via MailingList model)
  - **Content**: Report date, instructor, lesson scores, instructor notes, new qualifications
  - **Update Detection**: "Updated:" prefix in subject and banner for modified reports
  - **Qualifications**: Newly awarded qualifications highlighted with celebration styling
  - **Call to Action**: Link to student's training logbook

Email delivery is automatic when an instructor fills out an instruction report. The system detects both new reports and updates to existing reports, and intelligently tracks qualification status transitions (not just new qualifications, but also updates from unqualified to qualified status).

### **Analytics Integration**
Training data feeds into analytics for:
- Instructor performance metrics
- Student progress statistics
- Training phase completion rates
- Seasonal training activity patterns

## Common Workflows

### **New Student Onboarding**

```mermaid
flowchart TD
    A[Student Expresses Interest] --> B[Initial Ground School]
    B --> C[Medical/Prerequisites Check]
    C --> D[Training Assessment Meeting]
    D --> E[Training Plan Development]

    E --> F[Phase 1: Basic Controls]
    F --> G[Dual Instruction Flights]
    G --> H[Progress Evaluation]

    H --> I{Ready for Solo?}
    I -->|No| J[Additional Dual Time]
    I -->|Yes| K[Solo Preparation]

    J --> G
    K --> L[Pre-Solo Written Test]
    L --> M[Solo Skills Check]
    M --> N[First Solo Flight]

    N --> O[Post-Solo Training]
    O --> P[Cross-Country Preparation]
    P --> Q[License Check Ride]
    Q --> R[Certification Complete]

    style A fill:#e1f5fe
    style R fill:#e8f5e8
```

### **Lesson Documentation Process**

```mermaid
flowchart LR
    A[Pre-Flight Planning] --> B[Weather Briefing]
    B --> C[Aircraft Inspection]
    C --> D[Training Flight]
    D --> E[Post-Flight Debrief]

    E --> F[Instruction Report Creation]
    F --> G[Progress Assessment]
    G --> H[Email Sent to Student]
    H --> I[Next Lesson Planning]

    subgraph "Documentation Requirements"
        J[Flight Time Logged]
        K[Skills Practiced]
        L[Areas for Improvement]
        M[Student Performance]
        N[Safety Issues]
        O[Weather Conditions]
        P[New Qualifications]
    end

    F --> J
    F --> K
    F --> L
    F --> M
    F --> N
    F --> O
    F --> P

    subgraph "Email Content"
        Q[Lesson Scores]
        R[Instructor Notes]
        S[Qualifications Awarded]
        T[Logbook Link]
    end

    H --> Q
    H --> R
    H --> S
    H --> T
```

### **Instructor Assignment Process**

```mermaid
flowchart TD
    A[New Student Needs Instructor] --> B[Check Instructor Availability]
    B --> C[Match Experience Level]
    C --> D[Consider Student Preferences]
    D --> E[Assign Primary Instructor]

    E --> F[Initial Training Meeting]
    F --> G[Training Plan Agreement]
    G --> H[Lesson Scheduling]

    H --> I{Training Progressing?}
    I -->|Yes| J[Continue with Primary]
    I -->|Issues| K[Consider Instructor Change]

    K --> L[Student-Instructor Meeting]
    L --> M{Resolution Possible?}
    M -->|Yes| J
    M -->|No| N[Assign New Instructor]

    N --> O[Transition Meeting]
    O --> P[Continue Training]

    J --> Q[Regular Progress Reviews]
    P --> Q
```

## Known Gaps & Improvements

### **Current Strengths**
- ✅ Comprehensive lesson documentation
- ✅ Structured training phases and syllabus
- ✅ Integration with flight logging
- ✅ Progress tracking and reporting
- ✅ Instructor assignment management
- ✅ **Automated email notifications to students** (Issue #366)
- ✅ **Instructor team CC on instruction reports** (via MailingList)
- ✅ **Qualification tracking and notifications** (new and status changes)
- ✅ **Update detection for modified reports**
- ✅ **In-app notifications for students** (InstructionReport, GroundInstruction, Qualifications, Badges)

### **Identified Gaps**
- 🟡 **Calendar Integration**: No centralized scheduling system for lessons
- 🟡 **Student Portal**: Limited self-service options for students
- 🟡 **Mobile Access**: Instructors need mobile-friendly lesson entry
- 🟡 **Automated Scheduling**: Manual coordination between instructors and students
- 🟡 **Video/Photo Integration**: No multimedia support for training documentation

### **Improvement Opportunities**
- 🔄 **Smart Scheduling**: AI-assisted lesson scheduling based on weather, availability, and progress
- 🔄 **Progress Visualization**: Better charts and graphs for student progress tracking
- 🔄 **Standardized Checkrides**: Formal check ride scheduling and documentation
- 🔄 **Training Analytics**: Advanced metrics on training effectiveness and completion rates
- 🔄 **External Integration**: Connect with FAA databases and external training records

### **Training Quality Issues**
- 🔄 **Consistency Standards**: Ensure all instructors follow the same syllabus standards
- 🔄 **Competency Tracking**: Better validation that students master required skills
- 🔄 **Safety Documentation**: Enhanced safety incident tracking and lesson learned integration
- 🔄 **Instructor Development**: Continuing education tracking for instructors

### **Administrative Efficiency**
- 🔄 **Bulk Operations**: Tools for managing multiple students and lessons efficiently
- 🔄 **Report Automation**: Automated generation of training progress reports
- 🔄 **Compliance Tracking**: Ensure training meets regulatory requirements
- 🔄 **Resource Management**: Better allocation of aircraft and instructor time

## Student Communication System

### **Email Notification Flow**

When an instructor submits an instruction report, the system automatically delivers a comprehensive email to the student:

```mermaid
flowchart TD
    A[Instructor Fills Out Report] --> B{Report Type?}
    B -->|New Report| C[Create InstructionReport]
    B -->|Update| D[Update Existing Report]

    C --> E[Track New Qualifications]
    D --> E

    E --> F{Qualifications Changed?}
    F -->|Yes - New Record| G[Mark as New Qualification]
    F -->|Yes - Status Changed| H[Mark as Newly Qualified]
    F -->|No| I[No Qualifications to Report]

    G --> J[Prepare Email Content]
    H --> J
    I --> J

    J --> K[Render HTML Template]
    J --> L[Render Text Template]

    K --> M[Build Email Message]
    L --> M

    M --> N{Student Has Email?}
    N -->|No| O[Log Warning, Skip Email]
    N -->|Yes| P[Send to Student]

    P --> Q{Instructors Mailing List Exists?}
    Q -->|Yes| R[CC All Instructors]
    Q -->|No| S[No CC]

    R --> T[Remove Student from CC if Listed]
    T --> U[Deliver Email]
    S --> U

    U --> V{Email Sent Successfully?}
    V -->|Yes| W[Log Success, Continue]
    V -->|No| X[Log Error, Show Warning to Instructor]

    style A fill:#e1f5fe
    style U fill:#e8f5e8
    style O fill:#ffebee
    style X fill:#fff3e0
```

### **Email Content Design**

The instruction report email provides a professional, comprehensive summary of the training session:

**Subject Line:**
- New: `Instruction Report - [Student Name] - [Date]`
- Update: `Updated: Instruction Report - [Student Name] - [Date]`

**Visual Elements:**
- Club logo and branding
- Color-coded lesson scores:
  - 🟣 ① Introduced (purple)
  - 🔵 ② Practiced (blue)
  - 🟢 ③ Solo Standard (green)
  - 🟢 ④ Checkride Standard (dark green)
  - 🔴 ⚠ Needs Attention (red)
- Update banner for modified reports (yellow highlight)
- Celebration section for new qualifications (green highlight)

**Content Sections:**
1. Greeting with report date and instructor name
2. Update notice (if applicable)
3. New qualifications with expiration dates (if any)
4. Training items covered with color-coded scores
5. Instructor notes (rich text from TinyMCE)
6. Score legend for reference
7. Call-to-action button linking to student's training logbook

**Technical Implementation:**
- Multipart email (HTML + plain text)
- Responsive design for mobile devices
- From: `noreply@[domain_name]`
- Respects EMAIL_DEV_MODE for safe testing
- Automatic deduplication of student from CC list

### **Qualification Tracking Intelligence**

The system intelligently tracks qualification status changes:
- **New qualification**: Student didn't have this qualification before → Email includes it
- **Status transition**: Student had unqualified record, now marked qualified → Email includes it
- **Re-qualification**: Student already qualified, record updated → Not included (no change in status)

This ensures students receive notifications when they actually achieve a new qualification, not just when database records are updated.

## Related Workflows

- **[Member Lifecycle](02-member-lifecycle.md)**: How students become members and gain certifications
- **[Logsheet Workflow](04-logsheet-workflow.md)**: How training flights are logged and tracked
- **[Ground Instruction](08-ground-instruction.md)**: Classroom and theory training integration
- **[Knowledge Test Lifecycle](09-knowledge-test-lifecycle.md)**: Written examination process for students
- **[Duty Roster Workflow](05-duty-roster-workflow.md)**: How instructors are scheduled for duty

---

*The instruction workflow is critical for club growth and safety. Well-documented training ensures consistent, high-quality instruction that produces competent, safe pilots.*
