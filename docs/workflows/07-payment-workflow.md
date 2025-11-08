# Payment Workflow

## Manager Overview

The payment workflow manages the complete financial lifecycle of flight operations, from automatic cost calculation through payment collection and account reconciliation. This system integrates flight data with pricing rules to generate accurate member billing, supports various payment methods, and maintains comprehensive financial records.

**Key Stages:**
1. **Cost Calculation** - Automatic computation of flight costs based on operations data
2. **Member Billing** - Generation of individual member charges and notifications
3. **Payment Processing** - Collection and recording of payments from various sources
4. **Account Management** - Member account balances and payment history tracking
5. **Financial Reconciliation** - Period-end reconciliation and reporting

## Process Flow

```mermaid
flowchart TD
    A[Flight Completed] --> B[Extract Flight Data]
    B --> C[Calculate Tow Costs]
    B --> D[Calculate Rental Costs]

    C --> F[Apply Tow Rate Table]
    D --> G[Apply Hourly Rental Rates]

    F --> I[Total Cost Calculation]
    G --> I

    I --> J{Cost Splitting Required?}
    J -->|Yes| K[Apply Split Logic]
    J -->|No| L[Single Member Billing]

    K --> M[Calculate Individual Portions]
    M --> N[Create Multiple Member Charges]

    L --> O[Create Single Member Charge]
    N --> P[Update Member Accounts]
    O --> P

    P --> Q[Generate Payment Notifications]
    Q --> R[Send Member Billing Alerts]

    R --> S[Member Payment Actions]
    S --> T{Payment Method}

    T -->|Cash| U[Cash Payment Processing]
    T -->|Check| V[Check Payment Processing]
    T -->|Electronic| W[Electronic Payment Processing]
    T -->|Account Credit| X[Account Balance Application]

    U --> Y[Record Payment]
    V --> Y
    W --> Y
    X --> Y

    Y --> Z[Update Account Balance]
    Z --> AA[Payment Confirmation]
    AA --> BB[Generate Receipt]

    style A fill:#e1f5fe
    style BB fill:#e8f5e8
```

## Technical Implementation

### **Models Involved**
- **`logsheet.Flight`**: Source data for cost calculations
- **`logsheet.TowRate`**: Pricing for tow services by altitude
- **`logsheet.Glider`**: Aircraft rental rates and specifications
- **`members.Member`**: Account holders and payment recipients
- **Custom Payment Models**: Member account balances and payment records *(future implementation)*

### **Key Files**
- **Models**: `logsheet/models.py` - Cost calculation properties and methods
- **Views**: `logsheet/views.py` - Payment interface and account management
- **Utils**: `logsheet/utils.py` - Cost calculation algorithms
- **Forms**: `logsheet/forms.py` - Payment entry and account management forms
- **Analytics**: `analytics/queries.py` - Financial reporting and analysis

### **Cost Calculation Engine**

```mermaid
sequenceDiagram
    participant Flight as Flight Record
    participant System as Cost Calculator
    participant Rates as Rate Tables
    participant Member as Member Account
    participant Notifications as Notification System

    Flight->>System: Flight Completed Signal
    System->>Rates: Get Current Tow Rates
    System->>Rates: Get Aircraft Rental Rates
    System->>System: Calculate Base Costs

    alt Multi-Member Flight
        System->>System: Apply Cost Splitting Rules
        System->>Member: Update Multiple Accounts
    else Single Member Flight
        System->>Member: Update Single Account
    end

    System->>Notifications: Send Payment Notifications
    Notifications->>Member: Payment Due Alerts

    Member->>System: Submit Payment
    System->>Member: Update Account Balance
    System->>Member: Send Payment Confirmation
```

### **Cost Calculation Logic**

```mermaid
flowchart TD
    A[Flight Data Input] --> B[Tow Cost Calculation]
    A --> C[Rent Cost Calculation]

    B --> E[Release Altitude * Tow Rate]
    C --> F[Flight Duration * Hourly Rate]

    E --> H[Apply Member Discounts]
    F --> H

    H --> I{Cost Splitting?}
    I -->|Equal Split| J[Total Cost ÷ Participants]
    I -->|Custom Split| K[Apply Split Percentages]
    I -->|Pilot Pays All| L[Assign Full Cost to Pilot]

    J --> M[Individual Member Charges]
    K --> M
    L --> M

    M --> N[Account Balance Updates]
    N --> O[Payment Notifications]

    style E fill:#e3f2fd
    style F fill:#f3e5f5
    style G fill:#e8f5e8
```

### **Payment Processing States**

```mermaid
stateDiagram-v2
    [*] --> Pending: Flight Cost Calculated
    Pending --> Notified: Payment Notice Sent
    Notified --> PartialPaid: Partial Payment Received
    Notified --> FullyPaid: Full Payment Received
    PartialPaid --> FullyPaid: Remaining Balance Paid
    PartialPaid --> Overdue: Payment Deadline Passed
    Pending --> Overdue: No Payment Received
    Overdue --> FullyPaid: Late Payment Received
    Overdue --> Collections: Extended Non-payment
    FullyPaid --> [*]: Account Reconciled

    note right of FullyPaid
        Payment complete
        Receipt generated
        Account updated
    end note

    note right of Collections
        Administrative action
        May suspend privileges
    end note
```

### **Member Account Structure**

```mermaid
erDiagram
    Member {
        int id PK
        string name
        decimal account_balance
        string payment_status
        date last_payment_date
    }

    Flight {
        int id PK
        int pilot_id FK
        int instructor_id FK
        decimal tow_cost_calculated
        decimal rental_cost_calculated
        decimal total_cost
        string cost_split_method
        json cost_split_details
    }

    TowRate {
        int id PK
        int altitude_feet
        decimal rate_dollars
        date effective_date
        boolean active
    }

    Glider {
        int id PK
        string call_sign
        decimal rental_rate_per_hour
        boolean available
    }

    MemberCharge {
        int id PK
        int member_id FK
        int flight_id FK
        decimal amount
        string charge_type
        date charge_date
        string payment_status
        decimal amount_paid
        date payment_date
    }

    Payment {
        int id PK
        int member_id FK
        decimal amount
        string payment_method
        date payment_date
        string reference_number
        text notes
    }

    Member ||--o{ Flight : pilots
    Member ||--o{ Flight : instructs
    Member ||--o{ MemberCharge : charged
    Member ||--o{ Payment : makes
    Flight ||--o{ MemberCharge : generates
    Glider ||--o{ Flight : used_in
    TowRate ||--o{ Flight : applies_to
```

## Key Integration Points

### **Flight Operations Integration**
Payment calculations are triggered automatically by flight completion:

```mermaid
flowchart LR
    A[Flight Logged] --> B[Cost Calculation Triggered]
    B --> C[Member Account Updated]
    C --> D[Payment Notification Sent]
    D --> E[Member Payment Process]
    E --> F[Account Reconciliation]

    B --> G[Analytics Update]
    G --> H[Financial Reporting]
```

### **Member Account Management**
Payment workflow integrates with member lifecycle and privileges:

```mermaid
flowchart TD
    A[Member Account Status] --> B{Account Balance}
    B -->|Positive/Zero| C[Good Standing]
    B -->|Negative (Recent)| D[Payment Reminder]
    B -->|Negative (Extended)| E[Account Suspension]

    C --> F[Full Club Privileges]
    D --> G[Limited Warnings]
    E --> H[Restricted Access]

    F --> I[Continue Operations]
    G --> J[Payment Follow-up]
    H --> K[Administrative Review]

    J --> L{Payment Received?}
    L -->|Yes| C
    L -->|No| E
```

### **Analytics and Reporting Integration**
Payment data feeds financial analytics and reporting:

```mermaid
flowchart LR
    A[Payment Transactions] --> B[Revenue Analysis]
    A --> C[Member Payment Patterns]
    A --> D[Cost Center Analysis]

    B --> E[Club Financial Health]
    C --> F[Member Behavior Insights]
    D --> G[Operational Cost Tracking]

    E --> H[Management Reports]
    F --> I[Member Services]
    G --> J[Budget Planning]
```

## Common Workflows

### **Standard Flight Payment Process**

```mermaid
flowchart TD
    A[Member Completes Flight] --> B[Duty Officer Finalizes Flight Log]
    B --> C[System Calculates Costs]
    C --> D[Member Account Charged]
    D --> E[Email Notification Sent]

    E --> F[Member Reviews Charges]
    F --> G{Payment Method Choice}

    G -->|Online Payment| H[Electronic Payment Processing]
    G -->|Cash/Check| I[In-Person Payment]
    G -->|Account Credit| J[Balance Application]

    H --> K[Payment Confirmation]
    I --> L[Manual Payment Entry]
    J --> M[Balance Adjustment]

    K --> N[Receipt Generation]
    L --> N
    M --> N

    N --> O[Account Balance Updated]
    O --> P[Payment Complete]

    style A fill:#e1f5fe
    style P fill:#e8f5e8
```

### **Cost Splitting for Multi-Member Flights**

```mermaid
flowchart TD
    A[Multi-Member Flight] --> B[Identify Cost Split Method]
    B --> C{Split Type}

    C -->|Equal Split| D[Total Cost ÷ Number of Members]
    C -->|Percentage Split| E[Apply Custom Percentages]
    C -->|Pilot Pays Tow| F[Pilot: Tow, Others: Rental Portion]
    C -->|Instruction Flight| G[Student: All Costs, Instructor: None]

    D --> H[Calculate Equal Portions]
    E --> I[Calculate Percentage Portions]
    F --> J[Calculate Split by Cost Type]
    G --> K[Calculate Instruction Split]

    H --> L[Create Individual Charges]
    I --> L
    J --> L
    K --> L

    L --> M[Update Multiple Member Accounts]
    M --> N[Send Individual Notifications]
    N --> O[Process Individual Payments]
```

### **Monthly Account Reconciliation**

```mermaid
flowchart LR
    A[Month End Processing] --> B[Generate Member Statements]
    B --> C[Review Outstanding Balances]
    C --> D[Identify Payment Issues]

    D --> E{Account Status}
    E -->|Current| F[Send Statement]
    E -->|Past Due| G[Send Past Due Notice]
    E -->|Collections| H[Administrative Action]

    F --> I[Normal Operations]
    G --> J[Payment Follow-up]
    H --> K[Privilege Suspension]

    J --> L{Payment Response}
    L -->|Paid| I
    L -->|No Response| H

    K --> M[Member Contact]
    M --> N[Resolution Discussion]
```

## Known Gaps & Improvements

### **Current Strengths**
- ✅ Automatic cost calculation based on flight data
- ✅ Flexible cost splitting for multi-member flights
- ✅ Integration with flight operations and member management
- ✅ Real-time account balance updates
- ✅ Comprehensive notification system
- ✅ Analytics integration for financial reporting

### **Identified Gaps**
- 🟡 **Instructor Compensation**: No system for tracking or processing instructor payments for flight instruction services
- 🟡 **Payment Gateway Integration**: No automated electronic payment processing
- 🟡 **Mobile Payment Options**: Limited mobile-friendly payment interfaces
- 🟡 **Recurring Payments**: No support for membership dues or subscription billing
- 🟡 **Payment Plans**: No installment or deferred payment options
- 🟡 **External Accounting**: Limited integration with external accounting systems

### **Improvement Opportunities**
- 🔄 **Instructor Payment System**: Comprehensive system for billing students and compensating instructors for flight instruction services
- 🔄 **Online Payment Portal**: Full-featured member payment portal with multiple payment methods
- 🔄 **Payment Gateway Integration**: Integration with PayPal, Stripe, or other payment processors
- 🔄 **Mobile Payments**: Support for mobile wallets and contactless payments
- 🔄 **Automated Billing**: Recurring billing for membership dues and training programs
- 🔄 **Payment Analytics**: Advanced analytics on payment patterns and member behavior

### **Financial Management**
- 🔄 **QuickBooks Integration**: Direct integration with popular accounting software
- 🔄 **Tax Reporting**: Automated generation of tax-related reports and documents
- 🔄 **Budget Tracking**: Integration with club budgeting and financial planning
- 🔄 **Multi-Currency Support**: Support for international members and operations
- 🔄 **Financial Auditing**: Enhanced audit trails and compliance reporting

### **Member Experience**
- 🔄 **Payment History**: Comprehensive payment history and transaction tracking
- 🔄 **Account Statements**: Professional monthly and annual account statements
- 🔄 **Payment Reminders**: Intelligent reminder system with multiple notification methods
- 🔄 **Dispute Resolution**: Formal process for handling payment disputes and adjustments
- 🔄 **Payment Preferences**: Member-controlled payment preferences and methods

### **Administrative Efficiency**
- 🔄 **Bulk Payment Processing**: Tools for processing multiple payments efficiently
- 🔄 **Payment Matching**: Automated matching of payments to outstanding charges
- 🔄 **Exception Handling**: Better handling of payment exceptions and errors
- 🔄 **Refund Processing**: Streamlined refund and credit processing
- 🔄 **Collections Management**: Formal collections process and tracking

## Related Workflows

- **[Logsheet Workflow](04-logsheet-workflow.md)**: How flight operations generate the cost data for payment calculations
- **[Member Lifecycle](02-member-lifecycle.md)**: How member status affects payment privileges and account management
- **[Instruction Workflow](03-instruction-workflow.md)**: How training flights are billed and payment split between participants
- **[Maintenance Workflow](06-maintenance-workflow.md)**: How maintenance costs are tracked and allocated
- **[System Overview](01-system-overview.md)**: How payment processing fits into overall club financial management

---

*The payment workflow ensures accurate, timely collection of flight-related costs while providing members with convenient payment options. Effective payment processing is essential for club financial sustainability and member satisfaction.*
