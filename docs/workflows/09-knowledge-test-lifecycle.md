# Knowledge Test Lifecycle

## Manager Overview

The knowledge test lifecycle manages the complete process of written examinations from creation through administration, grading, and cleanup. This system supports both formal certification exams and informal knowledge checks, ensuring secure test administration while providing comprehensive progress tracking and feedback.

**Key Stages:**
1. **Test Creation** - Design and development of knowledge assessments
2. **Test Distribution** - Assignment and scheduling of tests for students
3. **Test Administration** - Secure test taking environment and monitoring
4. **Grading and Feedback** - Automated scoring and detailed feedback generation
5. **Data Management** - Results analysis and secure test data cleanup

## Process Flow

```mermaid
flowchart TD
    A[Test Requirements Identified] --> B[Create Test Questions]
    B --> C[Organize Questions by Topic]
    C --> D[Set Passing Criteria]
    D --> E[Review and Validate Test]
    
    E --> F[Assign Test to Students]
    F --> G[Student Notification]
    G --> H[Schedule Test Session]
    H --> I[Prepare Test Environment]
    
    I --> J[Student Begins Test]
    J --> K[Monitor Test Progress]
    K --> L[Student Submits Test]
    L --> M[Automatic Grading]
    
    M --> N{Passing Score?}
    N -->|Yes| O[Generate Pass Certificate]
    N -->|No| P[Generate Failure Report]
    
    O --> Q[Update Student Progress]
    P --> R[Identify Weak Areas]
    
    Q --> S[Send Success Notification]
    R --> T[Recommend Additional Study]
    
    S --> U[Record Achievement]
    T --> V[Schedule Retest]
    
    U --> W[Test Cycle Complete]
    V --> X[Additional Preparation]
    X --> H
    
    W --> Y[Archive Test Results]
    Y --> Z[Cleanup Test Data]
    
    style A fill:#e1f5fe
    style W fill:#e8f5e8
    style P fill:#fff3e0
```

## Technical Implementation

### **Models Involved**
- **`knowledgetest.TestPreset`**: Configurable test presets with category weight distributions
- **`knowledgetest.Question`**: Individual test questions and answers
- **`knowledgetest.QuestionCategory`**: Topic organization for questions
- **`knowledgetest.WrittenTestTemplate`**: Test definitions and configurations
- **`knowledgetest.WrittenTestAttempt`**: Individual test-taking sessions
- **`knowledgetest.WrittenTestAnswer`**: Student responses to questions
- **`knowledgetest.WrittenTestAssignment`**: Test assignments to students
- **`members.Member`**: Students taking tests and instructors creating them

### **Key Files**
- **Models**: `knowledgetest/models.py` - Test data structures and relationships
- **Views**: `knowledgetest/views.py` - Test administration interface
- **Forms**: `knowledgetest/forms.py` - Test creation and administration forms
- **Utils**: `knowledgetest/utils.py` - Scoring algorithms and test logic
- **Management**: `knowledgetest/management/commands/` - Automated test cleanup

### **Test Session Management**

```mermaid
sequenceDiagram
    participant Instructor as Instructor
    participant System as Manage2Soar
    participant Student as Student
    participant TestEngine as Test Engine
    participant Results as Results System
    
    Instructor->>System: Create/Assign Test
    System->>Student: Send Test Notification
    Student->>System: Request Test Session
    System->>TestEngine: Initialize Test Session
    
    TestEngine->>Student: Present Question 1
    Student->>TestEngine: Submit Answer
    TestEngine->>TestEngine: Record Response
    
    loop For Each Question
        TestEngine->>Student: Present Next Question
        Student->>TestEngine: Submit Answer
        TestEngine->>TestEngine: Record Response
    end
    
    Student->>TestEngine: Submit Complete Test
    TestEngine->>Results: Calculate Score
    Results->>System: Store Test Results
    
    alt Test Passed
        System->>Student: Send Pass Notification
        System->>Instructor: Report Success
    else Test Failed
        System->>Student: Send Study Recommendations
        System->>Instructor: Report Failure Details
    end
    
    System->>System: Schedule Test Cleanup
```

### **Question Bank Management**

```mermaid
flowchart TD
    A[Question Creation] --> B[Question Bank]
    B --> C[Category Organization]
    C --> D[Difficulty Levels]
    D --> E[Topic Tags]
    
    E --> F[Test Assembly]
    F --> G{Test Type}
    
    G -->|Preset-Based| H[Configurable Presets]
    G -->|Random Selection| I[Algorithm Selection]
    G -->|Manual Selection| J[Instructor Choice]
    G -->|Adaptive| K[Performance-Based]
    
    H --> L[Load Test Preset]
    L --> M[Apply Category Weights]
    I --> N[Balanced Topic Coverage]
    J --> O[Custom Test Design]
    K --> P[Dynamic Difficulty]
    
    M --> Q[Generated Test]
    N --> Q
    O --> Q
    P --> Q
    
    Q --> R[Test Validation]
    R --> S[Ready for Administration]
    
    style B fill:#e3f2fd
    style H fill:#fff3e0
    style S fill:#e8f5e8
```

### **Test Security and Integrity**

```mermaid
stateDiagram-v2
    [*] --> Created: Test Designed
    Created --> Scheduled: Student Assigned
    Scheduled --> Active: Test Session Begins
    Active --> InProgress: Student Answering
    InProgress --> Paused: Session Interrupted
    Paused --> InProgress: Session Resumed
    InProgress --> Submitted: Test Completed
    Submitted --> Graded: Automatic Scoring
    Graded --> Reviewed: Manual Review (if needed)
    Reviewed --> Finalized: Results Confirmed
    Finalized --> Archived: Results Stored
    Archived --> Deleted: Cleanup Period Expires
    
    note right of Active
        Secure test environment
        Anti-cheating measures
        Time tracking
    end note
    
    note right of Deleted
        Test data removed
        Privacy compliance
        Security maintained
    end note
```

### **Database Schema**

```mermaid
erDiagram
    Member {
        int id PK
        string name
        boolean instructor
    }
    
    TestPreset {
        int id PK
        string name UK
        text description
        json category_weights
        boolean is_active
        int sort_order
        datetime created_at
        datetime updated_at
    }
    
    QuestionCategory {
        int id PK
        string code UK
        text description
    }
    
    Question {
        int id PK
        int category_id FK
        text question
        string a
        string b
        string c
        string d
        string answer
        text explanation
        datetime lastupdated
        string updatedby
    }
    
    WrittenTestTemplate {
        int id PK
        string name
        text description
        int created_by_id FK
        datetime created_at
        decimal pass_percentage
        duration time_limit
    }
    
    WrittenTestTemplateQuestion {
        int id PK
        int template_id FK
        int question_id FK
        int order
    }
    
    WrittenTestAttempt {
        int id PK
        int template_id FK
        int student_id FK
        datetime started_at
        datetime completed_at
        decimal score_percentage
        boolean passed
        string status
    }
    
    WrittenTestAnswer {
        int id PK
        int attempt_id FK
        int question_id FK
        string selected_answer
        boolean correct
        datetime answered_at
    }
    
    WrittenTestAssignment {
        int id PK
        int template_id FK
        int student_id FK
        int instructor_id FK
        date due_date
        boolean completed
        datetime created_at
    }
    
    Member ||--o{ WrittenTestTemplate : creates
    Member ||--o{ WrittenTestAttempt : takes
    Member ||--o{ WrittenTestAssignment : assigned_to
    Member ||--o{ WrittenTestAssignment : created_by
    QuestionCategory ||--o{ Question : contains
    Question ||--o{ WrittenTestTemplateQuestion : used_in
    WrittenTestTemplate ||--o{ WrittenTestTemplateQuestion : includes
    WrittenTestTemplate ||--o{ WrittenTestAttempt : administered_as
    WrittenTestTemplate ||--o{ WrittenTestAssignment : assignments
    WrittenTestAttempt ||--o{ WrittenTestAnswer : contains
    Question ||--o{ WrittenTestAnswer : answered
```

## Key Integration Points

### **Ground Instruction Integration**
Knowledge tests validate ground school learning:

```mermaid
flowchart LR
    A[Ground Instruction Complete] --> B[Knowledge Check Available]
    B --> C[Student Takes Test]
    C --> D[Results Analysis]
    D --> E{Knowledge Gaps?}
    
    E -->|Yes| F[Additional Ground Study]
    E -->|No| G[Advance to Next Phase]
    
    F --> H[Targeted Review]
    H --> I[Retest Available]
    I --> C
    
    G --> J[Flight Training Authorization]
```

### **Training Progress Integration** 
Test results directly impact training progression:

```mermaid
flowchart TD
    A[Knowledge Test Result] --> B{Test Type}
    
    B -->|Phase Completion| C[Training Phase Sign-off]
    B -->|Skill Assessment| D[Training Lesson Planning]
    B -->|Safety Check| E[Safety Knowledge Update]
    B -->|Certification Prep| F[Certification Readiness]
    
    C --> G[Advance to Next Phase]
    D --> H[Customize Instruction]
    E --> I[Safety Compliance]
    F --> J[Schedule Check Ride]
    
    G --> K[Training Progress Update]
    H --> K
    I --> L[Safety Record Update]
    J --> M[Certification Process]
```

### **Analytics and Reporting Integration**
Test data provides valuable learning analytics:

```mermaid
flowchart LR
    A[Test Results] --> B[Student Performance Analytics]
    A --> C[Question Effectiveness Analysis]
    A --> D[Instructor Performance Metrics]
    
    B --> E[Learning Path Optimization]
    C --> F[Question Bank Improvement]
    D --> G[Instruction Quality Enhancement]
    
    E --> H[Personalized Learning]
    F --> I[Better Assessments]
    G --> J[Training Program Improvement]
```

### **Configurable Test Presets (Issue #135)**

The knowledge test system now supports database-driven test presets that replace hardcoded configurations:

```mermaid
flowchart TD
    A[Administrator Access] --> B[Django Admin Interface]
    B --> C[Manage Test Presets]
    C --> D{Action Required}
    
    D -->|Create New| E[Define Preset Name]
    D -->|Edit Existing| F[Select Existing Preset]
    D -->|Delete Unused| G[Remove Old Preset]
    
    E --> H[Set Category Weights]
    F --> I[Modify Category Weights]
    G --> J[Confirm Deletion Protection]
    
    H --> K[Configure Active Status]
    I --> L[Update Sort Order]
    J --> M{References Exist?}
    
    K --> N[Save New Preset]
    L --> O[Save Changes]
    M -->|Yes| P[Deletion Blocked]
    M -->|No| Q[Preset Deleted]
    
    N --> R[Preset Available for Use]
    O --> R
    P --> S[Error Message Shown]
    Q --> T[Preset Removed]
    
    R --> U[Instructors Can Use Preset]
    U --> V[Test Creation with Preset]
    V --> W[Automatic Form Population]
    
    style A fill:#e1f5fe
    style R fill:#e8f5e8
    style P fill:#ffebee
```

**Key Benefits:**
- **Flexibility**: Clubs can customize test configurations without code changes
- **Consistency**: Standardized test formats for specific aircraft or topics
- **Safety**: Deletion protection prevents accidental removal of active presets
- **Usability**: URL parameters automatically populate test creation forms

**Available Presets** (migrated from legacy system):
- **ASK21**: ASK-21 aircraft-specific test (73 questions)
- **PW5**: PW-5 aircraft-specific test (78 questions)
- **DISCUS**: Discus aircraft-specific test (47 questions)
- **ACRO**: Aerobatics-focused test (30 questions)
- **EMPTY**: Blank preset for custom test creation

## Common Workflows

### **Standard Knowledge Test Administration**

```mermaid
flowchart TD
    A[Student Ready for Knowledge Test] --> B[Instructor Assigns Test]
    B --> C[System Generates Test Session]
    C --> D[Student Receives Notification]
    D --> E[Student Schedules Test Time]
    
    E --> F[Test Environment Preparation]
    F --> G[Student Identity Verification]
    G --> H[Test Instructions Provided]
    H --> I[Test Session Begins]
    
    I --> J[Student Completes Questions]
    J --> K[Automatic Time Monitoring]
    K --> L{Time Remaining?}
    L -->|Yes| J
    L -->|No| M[Auto-Submit Test]
    
    J --> N[Student Submits Test]
    N --> O[Immediate Grading]
    M --> O
    
    O --> P[Results Calculation]
    P --> Q[Feedback Generation]
    Q --> R[Student Notification]
    R --> S[Instructor Notification]
    
    style A fill:#e1f5fe
    style S fill:#e8f5e8
```

### **Adaptive Testing Process**

```mermaid
flowchart LR
    A[Start Adaptive Test] --> B[Present Medium Difficulty Question]
    B --> C[Student Answers]
    C --> D{Answer Correct?}
    
    D -->|Yes| E[Increase Difficulty]
    D -->|No| F[Decrease Difficulty]
    
    E --> G[Select Harder Question]
    F --> H[Select Easier Question]
    
    G --> I[Present Next Question]
    H --> I
    I --> J[Student Answers]
    J --> K{Confidence Level Reached?}
    
    K -->|No| D
    K -->|Yes| L[Calculate Final Score]
    L --> M[Generate Results]
```

### **Test Data Cleanup Process**

```mermaid
flowchart TD
    A[Scheduled Cleanup Process] --> B[Identify Expired Test Sessions]
    B --> C[Archive Essential Results Data]
    C --> D[Remove Detailed Question Responses]
    D --> E[Delete Personal Test Data]
    
    E --> F[Preserve Aggregate Statistics]
    F --> G[Update Analytics Data]
    G --> H[Generate Cleanup Report]
    H --> I[Notify Administrators]
    
    I --> J{Manual Review Required?}
    J -->|Yes| K[Administrative Review]
    J -->|No| L[Cleanup Complete]
    
    K --> M[Approve Final Cleanup]
    M --> L
    
    style A fill:#e1f5fe
    style L fill:#e8f5e8
```

## Known Gaps & Improvements

### **Current Strengths**
- ✅ **Configurable test presets** - Database-driven test configurations replace hardcoded values
- ✅ Comprehensive question bank management system
- ✅ Secure test administration with time tracking
- ✅ Automatic grading and immediate feedback
- ✅ Integration with training progress tracking
- ✅ Privacy-compliant data cleanup processes
- ✅ Detailed analytics on test performance

### **Identified Gaps**
- 🟡 **Advanced Question Types**: Limited support for multimedia, drag-and-drop, or interactive questions
- 🟡 **Anti-Cheating Measures**: Basic security, could be enhanced with proctoring features
- 🟡 **Mobile Testing**: Limited mobile interface for test taking
- 🟡 **Offline Testing**: No support for offline test administration
- 🟡 **Question Authoring**: Limited tools for creating complex questions

### **Improvement Opportunities**
- 🔄 **Enhanced Question Types**: Support for multimedia, simulations, and interactive assessments
- 🔄 **AI-Powered Testing**: Adaptive testing with AI-driven question selection
- 🔄 **Remote Proctoring**: Secure remote test administration with monitoring
- 🔄 **Collaborative Authoring**: Better tools for multiple instructors to create and review questions
- 🔄 **Learning Analytics**: Advanced analytics on learning patterns and effectiveness

### **Test Security and Integrity**
- 🔄 **Advanced Anti-Cheating**: Browser lockdown, keystroke monitoring, and behavior analysis
- 🔄 **Identity Verification**: Biometric or multi-factor authentication for high-stakes tests
- 🔄 **Question Pool Management**: Larger question pools with better randomization
- 🔄 **Secure Delivery**: Enhanced encryption and secure test delivery mechanisms
- 🔄 **Audit Trails**: Comprehensive logging of all test administration activities

### **Accessibility and Usability**
- 🔄 **Accessibility Compliance**: Full WCAG compliance for students with disabilities
- 🔄 **Multi-language Support**: Tests and interfaces in multiple languages
- 🔄 **Customizable Interface**: Adaptable interface for different learning styles
- 🔄 **Performance Optimization**: Faster loading and responsive design
- 🔄 **Offline Capability**: Support for offline test taking with later synchronization

### **Analytics and Reporting**
- 🔄 **Predictive Analytics**: Predict student success and identify at-risk learners
- 🔄 **Question Analytics**: Deep analysis of question effectiveness and bias
- 🔄 **Instructor Dashboards**: Comprehensive dashboards for instructors and administrators
- 🔄 **Competency Mapping**: Link test results to specific competencies and skills
- 🔄 **Longitudinal Analysis**: Track learning progress over extended periods

## Related Workflows

- **[Ground Instruction](08-ground-instruction.md)**: How ground school prepares students for knowledge tests
- **[Instruction Workflow](03-instruction-workflow.md)**: How knowledge tests integrate with flight training progression
- **[Member Lifecycle](02-member-lifecycle.md)**: How knowledge tests support member development and certification
- **[System Overview](01-system-overview.md)**: How knowledge testing fits into overall training and assessment systems

---

*The knowledge test lifecycle ensures comprehensive, secure, and fair assessment of student learning. Effective testing validates training outcomes and supports continuous improvement in instruction quality.*