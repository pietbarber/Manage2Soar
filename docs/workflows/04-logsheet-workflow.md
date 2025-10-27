# Logsheet Workflow

## Manager Overview

The logsheet workflow is the operational heart of the soaring club, managing daily flight operations from dawn to dusk. It encompasses logsheet creation, flight logging, cost calculation, maintenance tracking, and end-of-day reconciliation. This workflow captures all flight activity and integrates with billing, instruction, and maintenance systems.

**Key Stages:**
1. **Pre-Operations Setup** - Create daily logsheet and assign duty crew
2. **Flight Operations** - Log flights, track aircraft, manage operations
3. **Cost Calculation** - Calculate tow fees, rental costs, and member charges
4. **Maintenance Tracking** - Document aircraft issues and maintenance needs
5. **End-of-Day Closeout** - Reconcile flights, finalize costs, archive records

## Process Flow

```mermaid
flowchart TD
    A[Duty Officer Arrives] --> B[Check Weather/Conditions]
    B --> C[Create/Open Daily Logsheet]
    C --> D[Aircraft Pre-flight Inspections]
    D --> E[Operations Begin]
    
    E --> F[Member Requests Flight]
    F --> G[Check Aircraft Availability]
    G --> H[Assign Aircraft/Instructor]
    H --> I[Log Flight Start]
    
    I --> J[Flight in Progress]
    J --> K[Flight Lands]
    K --> L[Log Flight End]
    L --> M[Calculate Costs]
    
    M --> N{Training Flight?}
    N -->|Yes| O[Link to Training Record]
    N -->|No| P[Standard Flight Processing]
    
    O --> Q[Update Training Progress]
    P --> R[Member Cost Notification]
    Q --> R
    
    R --> S{More Flights?}
    S -->|Yes| F
    S -->|No| T[End of Operations]
    
    T --> U[Aircraft Post-flight Checks]
    U --> V{Maintenance Issues?}
    V -->|Yes| W[Log Maintenance Item]
    V -->|No| X[Close Logsheet]
    
    W --> Y[Notify Maintenance Team]
    Y --> X
    X --> Z[Generate Daily Reports]
    Z --> AA[Archive Logsheet]
    
    style A fill:#e1f5fe
    style AA fill:#e8f5e8
    style W fill:#fff3e0
```

## Technical Implementation

### **Models Involved**
- **`logsheet.Logsheet`**: Daily operations record
- **`logsheet.Flight`**: Individual flight records
- **`logsheet.Glider`**: Aircraft fleet management
- **`logsheet.Towplane`**: Tow aircraft management
- **`logsheet.Airfield`**: Operations locations
- **`logsheet.TowRate`**: Pricing for tow services
- **`logsheet.MaintenanceIssue`**: Aircraft maintenance tracking
- **`members.Member`**: Pilots, instructors, and duty officers

### **Key Files**
- **Models**: `logsheet/models.py` - Flight operations data structures
- **Views**: `logsheet/views.py` - Flight logging interface
- **Forms**: `logsheet/forms.py` - Flight entry and editing forms
- **Utils**: `logsheet/utils.py` - Cost calculations and business logic
- **Signals**: `logsheet/signals.py` - Automated notifications and analytics updates

### **Daily Operations Sequence**

```mermaid
sequenceDiagram
    participant DO as Duty Officer  
    participant System as Manage2Soar
    participant Member as Club Member
    participant Instructor as Instructor
    participant Maintenance as Maintenance Team
    participant Analytics as Analytics
    
    DO->>System: Create Daily Logsheet
    System->>System: Initialize Aircraft Status
    DO->>System: Record Weather Conditions
    
    Member->>DO: Request Flight
    DO->>System: Check Aircraft Availability
    System->>DO: Show Available Aircraft
    DO->>System: Assign Aircraft & Log Flight Start
    
    alt Training Flight
        System->>Instructor: Notify of Training Flight
        Instructor->>System: Acknowledge Assignment
    end
    
    DO->>System: Log Flight Landing
    System->>System: Calculate Flight Costs
    System->>Member: Send Cost Notification
    
    alt Maintenance Issue Found
        DO->>System: Log Maintenance Issue
        System->>Maintenance: Send Issue Notification
    end
    
    DO->>System: Close Daily Operations
    System->>Analytics: Update Flight Statistics
    System->>System: Generate Daily Reports
```

### **Flight Cost Calculation Engine**

```mermaid
flowchart LR
    A[Flight Data] --> B[Calculate Tow Cost]
    A --> C[Calculate Rental Cost]
    A --> D[Check Split Arrangements]
    
    B --> E[Release Altitude × Rate]
    C --> F[Flight Time × Hourly Rate]
    D --> G[Apply Cost Splitting]
    
    E --> H[Base Tow Cost]
    F --> I[Base Rental Cost]
    G --> J[Member Portions]
    
    H --> K[Apply Member Discounts]
    I --> K
    J --> K
    
    K --> L[Final Member Costs]
    L --> M[Generate Billing Records]
    M --> N[Send Payment Notifications]
```

### **Aircraft Status Tracking**

```mermaid
stateDiagram-v2
    [*] --> Available: Daily Checkout
    Available --> PreFlight: Flight Assigned
    PreFlight --> InUse: Pre-flight Complete
    InUse --> PostFlight: Flight Landed
    PostFlight --> Available: Post-flight OK
    PostFlight --> Maintenance: Issue Found
    Maintenance --> Available: Issue Resolved
    Maintenance --> OutOfService: Major Issue
    OutOfService --> Maintenance: Repair Started
    Available --> Hangar: End of Day
    Hangar --> [*]: Operations Closed
    
    note right of Maintenance
        Tracked in MaintenanceIssue
        Notifications sent automatically
    end note
    
    note right of OutOfService
        Aircraft unavailable
        Until repairs complete
    end note
```

### **Database Schema**

```mermaid
erDiagram
    Logsheet {
        int id PK
        date log_date UK
        int airfield_id FK
        int duty_officer_id FK
        int assistant_duty_officer_id FK
        int instructor_id FK
        int tow_pilot_id FK
        text weather_conditions
        boolean operations_closed
        datetime created_at
        datetime updated_at
    }
    
    Flight {
        int id PK
        int logsheet_id FK
        int pilot_id FK
        int instructor_id FK
        int glider_id FK
        int towplane_id FK
        datetime flight_start
        datetime flight_end
        int release_altitude
        string flight_type
        decimal tow_cost_calculated
        decimal rental_cost_calculated
        text remarks
    }
    
    Glider {
        int id PK
        string call_sign UK
        string model
        decimal rental_rate_per_hour
        boolean available
        date last_inspection
        decimal total_flight_hours
    }
    
    Towplane {
        int id PK
        string call_sign UK
        string model
        boolean available
        decimal total_flight_hours
    }
    
    MaintenanceIssue {
        int id PK
        int glider_id FK
        int reported_by_id FK
        date reported_date
        text description
        string priority
        string status
        decimal estimated_cost
        date resolved_date
    }
    
    TowRate {
        int id PK
        int altitude_feet
        decimal rate_dollars
        date effective_date
    }
    
    Airfield {
        int id PK
        string name UK
        string identifier
        text description
        decimal elevation_feet
    }
    
    Logsheet ||--o{ Flight : contains
    Glider ||--o{ Flight : flown_in
    Towplane ||--o{ Flight : towed_by
    Member ||--o{ Flight : pilots
    Member ||--o{ Flight : instructs
    Member ||--o{ Logsheet : duty_officer
    Airfield ||--o{ Logsheet : location
    Glider ||--o{ MaintenanceIssue : has_issues
    Member ||--o{ MaintenanceIssue : reports
```

## Key Integration Points

### **Training Integration**
Flight operations seamlessly integrate with instruction:

```mermaid
flowchart LR
    A[Training Lesson Scheduled] --> B[Flight Assignment]
    B --> C[Duty Officer Logs Flight]
    C --> D[Instructor Completes Lesson]
    D --> E[Flight Linked to Training]
    E --> F[Progress Updated]
    F --> G[Training Analytics Updated]
```

### **Payment Processing Integration**
Flight costs automatically flow to payment systems:

```mermaid
flowchart TD
    A[Flight Completed] --> B[Cost Calculation]
    B --> C[Member Account Update]
    C --> D[Payment Notification]
    D --> E[Member Payment]
    E --> F[Account Reconciliation]
    
    B --> G[Split Cost Calculation]
    G --> H[Multiple Member Billing]
    H --> I[Individual Notifications]
```

### **Maintenance Workflow Integration**
Maintenance issues are tracked and resolved:

```mermaid
flowchart LR
    A[Issue Discovered] --> B[Maintenance Report]
    B --> C[Priority Assessment]
    C --> D[Repair Assignment]
    D --> E[Work Completion]
    E --> F[Aircraft Return to Service]
    
    B --> G[Notification System]
    G --> H[Alert Maintenance Team]
    G --> I[Inform Duty Officers]
    G --> J[Update Analytics]
```

## Common Workflows

### **Standard Flight Operations Day**

```mermaid
flowchart TD
    A[0700: Duty Officer Arrival] --> B[0730: Weather Check]
    B --> C[0800: Aircraft Inspection]
    C --> D[0830: Create Daily Logsheet]
    D --> E[0900: Operations Begin]
    
    E --> F[1000-1700: Flight Operations]
    F --> G[Flight Requests]
    G --> H[Aircraft Assignment]
    H --> I[Flight Logging]
    I --> J[Cost Calculation]
    J --> K[Member Notification]
    
    K --> L{More Flights?}
    L -->|Yes| G
    L -->|No| M[1700: Operations End]
    
    M --> N[Aircraft Secure]
    N --> O[Maintenance Check]
    O --> P[Logsheet Review]
    P --> Q[Daily Reports]
    Q --> R[Logsheet Archive]
    
    style A fill:#e1f5fe
    style R fill:#e8f5e8
```

### **Flight Cost Splitting Process**

```mermaid
flowchart TD
    A[Multiple Members on Flight] --> B[Identify Cost Split Type]
    B --> C{Split Method}
    
    C -->|Equal Split| D[Divide Costs Equally]
    C -->|Custom Split| E[Apply Custom Percentages]
    C -->|Pilot Pays All| F[Assign Full Cost to Pilot]
    
    D --> G[Calculate Individual Portions]
    E --> G
    F --> G
    
    G --> H[Update Member Accounts]
    H --> I[Send Individual Notifications]
    I --> J[Generate Split Summary]
    J --> K[Archive Cost Records]
```

### **Maintenance Issue Resolution**

```mermaid
flowchart LR
    A[Issue Reported] --> B[Priority Classification]
    B --> C{Severity Level}
    
    C -->|Critical| D[Ground Aircraft Immediately]
    C -->|High| E[Schedule Urgent Repair]
    C -->|Medium| F[Plan Routine Maintenance]
    C -->|Low| G[Add to Maintenance List]
    
    D --> H[Emergency Repair]
    E --> I[Priority Scheduling]
    F --> J[Regular Maintenance]
    G --> K[Future Planning]
    
    H --> L[Return to Service]
    I --> L
    J --> L
    K --> M[Maintenance Backlog]
    
    L --> N[Update Aircraft Status]
    M --> O[Schedule Future Work]
```

## Known Gaps & Improvements

### **Current Strengths**
- ✅ Comprehensive flight logging and tracking
- ✅ Integrated cost calculation and billing
- ✅ Real-time aircraft status management
- ✅ Maintenance issue tracking and notifications
- ✅ Training flight integration
- ✅ Detailed reporting and analytics integration

### **Identified Gaps**
- 🟡 **Real-time Updates**: Limited real-time collaboration between duty officers
- 🟡 **Mobile Interface**: Duty officers need better mobile access for field operations
- 🟡 **Weather Integration**: No automated weather data integration
- 🟡 **Aircraft Scheduling**: No advance booking system for aircraft
- 🟡 **Digital Signatures**: Paper-based sign-offs for maintenance and inspections

### **Improvement Opportunities**
- 🔄 **Predictive Analytics**: Use historical data to predict busy periods and maintenance needs
- 🔄 **Automated Notifications**: Enhanced notification system for operations status
- 🔄 **Integration APIs**: Connect with external flight tracking and weather systems
- 🔄 **Workflow Automation**: Reduce manual data entry and repetitive tasks
- 🔄 **Advanced Reporting**: More sophisticated analytics and operational metrics

### **Operational Efficiency**
- 🔄 **Queue Management**: Better system for managing flight requests during busy periods
- 🔄 **Resource Optimization**: AI-assisted aircraft and instructor scheduling
- 🔄 **Batch Operations**: Tools for processing multiple flights efficiently
- 🔄 **Error Prevention**: Enhanced validation to prevent data entry errors
- 🔄 **Backup Procedures**: Improved contingency planning for system outages

### **Safety and Compliance**
- 🔄 **Safety Reporting**: Enhanced safety incident tracking and analysis
- 🔄 **Regulatory Compliance**: Automated compliance checking and reporting
- 🔄 **Audit Trail**: Complete tracking of all changes and modifications
- 🔄 **Risk Management**: Integration with safety management systems

## Related Workflows

- **[Duty Roster Workflow](05-duty-roster-workflow.md)**: How duty officers are assigned to manage operations
- **[Instruction Workflow](03-instruction-workflow.md)**: How training flights are integrated with operations
- **[Payment Workflow](07-payment-workflow.md)**: How flight costs are calculated and collected
- **[Maintenance Workflow](06-maintenance-workflow.md)**: How aircraft maintenance is tracked and managed
- **[Member Lifecycle](02-member-lifecycle.md)**: How member status affects flight privileges and costs

---

*The logsheet workflow is essential for safe, efficient flight operations. It provides the data foundation that drives instruction tracking, financial management, and operational analytics throughout the club.*