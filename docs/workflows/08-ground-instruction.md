# Ground Instruction Workflow

## Manager Overview

The ground instruction workflow manages the logging and tracking of individual ground-based instructional sessions between instructors and students. This is a simple system for recording one-on-one briefings, theoretical discussions, and lesson-specific training that supports flight instruction and student development.

**Key Stages:**
1. **Session Logging** - Record individual ground instruction sessions
2. **Content Documentation** - Document topics covered and lesson progress
3. **Progress Tracking** - Track student advancement through training lessons
4. **Performance Scoring** - Score student performance on specific training lessons

## Process Flow

```mermaid
flowchart TD
    A[Instructor Plans Session] --> B[Schedule with Student]
    B --> C[Conduct Ground Instruction]

    C --> D{Session Type}
    D -->|Pre-Flight Brief| E[Flight Preparation Discussion]
    D -->|Post-Flight Debrief| F[Flight Review & Analysis]
    D -->|Theory Session| G[Aerodynamics/Procedures Study]
    D -->|Knowledge Review| H[Lesson-Specific Training]

    E --> I[Document Session Details]
    F --> I
    G --> I
    H --> I

    I --> J[Score Individual Lessons]
    J --> K[Save Session Record]
    K --> L[Update Student Progress]
    L --> M[Notify Student]
    M --> N[Session Complete]

    style A fill:#e1f5fe
    style N fill:#e8f5e8
```

## Technical Implementation

### **Models Involved**
- **`instructors.GroundInstruction`**: Individual ground instruction sessions
- **`instructors.GroundLessonScore`**: Lesson-specific performance scores
- **`instructors.TrainingLesson`**: Training syllabus lesson definitions
- **`instructors.TrainingPhase`**: Organized training phases
- **`members.Member`**: Students and instructors

### **Key Files**
- **Models**: `instructors/models.py` - Ground instruction data structures
- **Views**: `instructors/views.py` - Ground instruction logging interface
- **Forms**: `instructors/forms.py` - Ground instruction session forms
- **Templates**: `instructors/templates/` - Ground instruction logging UI
- **Signals**: `instructors/signals.py` - Progress tracking and notifications

### **Ground Instruction Session Logging**

```mermaid
sequenceDiagram
    participant Instructor as Instructor
    participant System as Manage2Soar
    participant Student as Student
    participant Progress as Progress Tracker

    Instructor->>System: Access Ground Instruction Form
    System->>System: Load Training Lessons
    System->>Instructor: Display Session Form

    Instructor->>System: Complete Session Details
    Instructor->>System: Score Individual Lessons
    Instructor->>System: Save Ground Session

    System->>System: Create GroundInstruction Record
    System->>System: Save GroundLessonScore Records

    System->>Progress: Update Student Progress
    System->>Student: Send Session Notification
    System->>Instructor: Confirm Session Saved
```

### **Ground Instruction Session Types**

```mermaid
flowchart TD
    A[Ground Instruction Session] --> B[Pre-Flight Briefing]
    A --> C[Post-Flight Debrief]
    A --> D[Theory Discussion]
    A --> E[Lesson Review]

    B --> F[Weather Analysis]
    B --> G[Flight Planning]
    B --> H[Aircraft Systems]
    B --> I[Safety Considerations]

    C --> J[Flight Performance Review]
    C --> K[Learning Points Discussion]
    C --> L[Areas for Improvement]
    C --> M[Next Steps Planning]

    D --> N[Aerodynamics Concepts]
    D --> O[Regulations & Procedures]
    D --> P[Emergency Procedures]

    E --> Q[Lesson-Specific Scoring]
    E --> R[Progress Assessment]
    E --> S[Remedial Training]

    style B fill:#e3f2fd
    style C fill:#f3e5f5
    style D fill:#fff3e0
    style E fill:#e8f5e8
```

### **Learning Progress Tracking**

```mermaid
stateDiagram-v2
    [*] --> Enrolled: Student Registration
    Enrolled --> InProgress: Begin Ground School
    InProgress --> TopicComplete: Complete Topic
    TopicComplete --> Assessment: Knowledge Check
    Assessment --> Passed: Test Passed
    Assessment --> NeedsReview: Test Failed
    NeedsReview --> InProgress: Additional Study
    Passed --> InProgress: Next Topic
    Passed --> PhaseComplete: All Topics Done
    PhaseComplete --> NextPhase: Advance to Next Phase
    PhaseComplete --> Graduated: Ground School Complete
    NextPhase --> InProgress: Continue Training
    Graduated --> [*]: Training Complete

    note right of Assessment
        Knowledge tests validate
        understanding of topics
    end note

    note right of NeedsReview
        Additional study required
        before advancing
    end note
```

### **Database Schema**

```mermaid
erDiagram
    Member {
        int id PK
        string username
        string first_name
        string last_name
        boolean instructor
    }

    TrainingPhase {
        int id PK
        int number
        string name
    }

    TrainingLesson {
        int id PK
        string code
        string title
        text description
        int phase_id FK
        string far_requirement
        string pts_reference
    }

    GroundInstruction {
        int id PK
        int student_id FK
        int instructor_id FK
        date date
        string location
        duration duration
        text notes
        datetime created_at
        datetime updated_at
    }

    GroundLessonScore {
        int id PK
        int session_id FK
        int lesson_id FK
        string score
    }

    Member ||--o{ GroundInstruction : student
    Member ||--o{ GroundInstruction : instructor  
    TrainingPhase ||--o{ TrainingLesson : contains
    GroundInstruction ||--o{ GroundLessonScore : session
    TrainingLesson ||--o{ GroundLessonScore : lesson
```

## Key Integration Points

### **Flight Instruction Integration**
Ground instruction coordinates closely with flight training:

```mermaid
flowchart LR
    A[Ground School Topics] --> B[Flight Lesson Prerequisites]
    B --> C[Pre-Flight Briefing]
    C --> D[Flight Training]
    D --> E[Post-Flight Debrief]
    E --> F[Ground Knowledge Reinforcement]

    A --> G[Knowledge Test Preparation]
    G --> H[Written Examination]
    H --> I[Flight Test Readiness]
```

### **Progress Tracking Integration**
Ground instruction integrates with overall student progress tracking:

```mermaid
flowchart TD
    A[Ground Instruction Session] --> B[Lesson Scores Recorded]
    B --> C[Student Progress Updated]
    C --> D[Training Record Updated]
    D --> E[Progress Visible to Student]
    E --> F[Instructor Progress Reports]
```

### **Flight Training Integration**
Ground instruction complements flight training activities:

```mermaid
flowchart LR
    A[Pre-Flight Brief] --> B[Flight Lesson]
    B --> C[Post-Flight Debrief]
    C --> D[Ground Session Logged]
    D --> E[Lesson Scores Updated]
    E --> F[Next Flight Planned]
```

## Common Workflows

### **Individual Ground Instruction Session**

```mermaid
flowchart TD
    A[Instructor Identifies Need] --> B[Schedule Session with Student]
    B --> C[Prepare Session Content]
    C --> D[Conduct Ground Instruction]

    D --> E[Document Session Details]
    E --> F[Score Relevant Lessons]
    F --> G[Save Session to System]
    G --> H[Student Receives Notification]

    H --> I[Review Session in Training Record]
    I --> J[Plan Follow-up Sessions]

    style A fill:#e1f5fe
    style J fill:#e8f5e8
```

### **Pre-Flight Briefing Workflow**

```mermaid
flowchart LR
    A[Flight Lesson Scheduled] --> B[Pre-Flight Ground Brief]
    B --> C[Review Lesson Objectives]
    C --> D[Discuss Weather/Conditions]
    D --> E[Aircraft Systems Review]

    E --> F[Flight Training Session]
    F --> G[Post-Flight Debrief]
    G --> H[Log Ground Session]
    H --> I[Score Lesson Performance]
    I --> J[Update Training Record]
```

### **Theory Discussion Session**

```mermaid
flowchart TD
    A[Student Has Questions] --> B[Schedule Theory Session]
    B --> C[Prepare Reference Materials]
    C --> D[Conduct Discussion]

    D --> E[Cover Aerodynamics Concepts]
    D --> F[Review Regulations]
    D --> G[Discuss Procedures]

    E --> H[Document Session]
    F --> H
    G --> H
    H --> I[Score Understanding]
    I --> J[Plan Additional Study]
```

## Known Gaps & Improvements

### **Current Strengths**
- ✅ Simple session logging for individual ground instruction
- ✅ Integration with flight instruction progress tracking
- ✅ Lesson-specific scoring and progress monitoring
- ✅ Automatic student notifications of completed sessions
- ✅ Historical session tracking and instructor records

### **Identified Gaps**
- 🟡 **Group Sessions**: No support for formal group classes or ground schools
- 🟡 **Session Scheduling**: No built-in scheduling system for ground instruction
- 🟡 **Content Management**: No formal curriculum or materials management
- 🟡 **Attendance Tracking**: Limited to individual sessions, no group attendance
- 🟡 **Knowledge Testing**: No formal testing integration specific to ground instruction

### **Improvement Opportunities**
- 🔄 **Formal Ground School**: Support for scheduled group classes and attendance tracking
- 🔄 **Session Scheduling**: Calendar integration and scheduling tools for ground instruction
- 🔄 **Curriculum Management**: Structured ground school curriculum and materials
- 🔄 **Student Portal**: Self-service access for students to view ground instruction history
- 🔄 **Progress Analytics**: Enhanced analytics on ground instruction effectiveness
- 🔄 **Payment Integration**: Ground instruction billing and payment tracking (currently no payment structure exists)

### **Content and Materials**
- 🔄 **Reference Materials**: Library of ground school materials and references
- 🔄 **Multimedia Content**: Support for videos, presentations, and interactive content
- 🔄 **External Resources**: Integration with external training materials and resources
- 🔄 **Content Organization**: Better organization and categorization of training materials
- 🔄 **Mobile Access**: Mobile-optimized access to ground instruction materials

### **Assessment and Evaluation**
- 🔄 **Knowledge Testing**: Integration with formal knowledge testing system
- 🔄 **Progress Visualization**: Better visual representation of student progress
- 🔄 **Competency Tracking**: Formal competency-based progression tracking
- 🔄 **Session Analytics**: Analytics on ground instruction session effectiveness
- 🔄 **Instructor Feedback**: Enhanced feedback mechanisms for instructors

### **Communication and Planning**
- 🔄 **Session Planning**: Tools for planning and preparing ground instruction sessions
- 🔄 **Student Communication**: Enhanced communication between instructors and students
- 🔄 **Session Reminders**: Automated reminders for scheduled ground instruction
- 🔄 **Progress Reports**: Automated progress reports for students and instructors
- 🔄 **Calendar Integration**: Integration with club and personal calendars

## Related Workflows

- **[Instruction Workflow](03-instruction-workflow.md)**: How ground instruction integrates with flight training
- **[Knowledge Test Lifecycle](09-knowledge-test-lifecycle.md)**: How ground instruction prepares students for testing
- **[Member Lifecycle](02-member-lifecycle.md)**: How ground school supports member development and progression
- **[System Overview](01-system-overview.md)**: How ground instruction fits into overall training programs

---

*Ground instruction is essential for safe, knowledgeable pilots. Effective ground school programs build the theoretical foundation that supports practical flight training and lifelong learning.*
