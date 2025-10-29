# Models in knowledgetest/models.py

This document describes all models in `knowledgetest/models.py` and includes the database schema for this app.

---

## Database Schema

```mermaid
erDiagram
    Member ||--o{ WrittenTestTemplate : created_by
    Member ||--o{ WrittenTestAttempt : student
    Member ||--o{ WrittenTestAssignment : assigned_to
    Member ||--o{ WrittenTestAssignment : created_by
    
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
        boolean active
        int time_limit_minutes
        decimal passing_score
    }
    
    WrittenTestTemplateQuestion {
        int id PK
        int template_id FK
        int question_id FK
        int question_order
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
        int assigned_to_id FK
        int created_by_id FK
        date due_date
        boolean completed
        datetime created_at
    }
    
    QuestionCategory ||--o{ Question : categorizes
    WrittenTestTemplate ||--o{ WrittenTestTemplateQuestion : contains
    Question ||--o{ WrittenTestTemplateQuestion : used_in
    WrittenTestTemplate ||--o{ WrittenTestAttempt : attempts
    WrittenTestTemplate ||--o{ WrittenTestAssignment : assignments
    WrittenTestAttempt ||--o{ WrittenTestAnswer : answers
    Question ||--o{ WrittenTestAnswer : answered
```

## TestPreset
- **Purpose:** Configurable test presets that define question distribution across categories for standardized tests.
- **Fields:** name (unique), description, category_weights (JSONField), is_active, sort_order, created_at, updated_at
- **Key Features:** Database-driven presets replace hardcoded test configurations, deletion protection for referenced presets
- **Usage:** Staff can manage presets via Django admin, presets can be applied via URL parameters in test creation

## QuestionCategory
- **Purpose:** Groups questions by category code and description.
- **Fields:** code, description

## Question
- **Purpose:** Represents a single test question and its possible answers.
- **Fields:** category (FK), question, a, b, c, d, answer, explanation, lastupdated, updatedby

## WrittenTestTemplate
- **Purpose:** Defines a template for a written test (set of questions).
- **Fields:** name, description, created_by, created_at

## WrittenTestTemplateQuestion
- **Purpose:** Associates questions with a template and defines order.
- **Fields:** template (FK), question (FK), order

## WrittenTestAttempt
- **Purpose:** Represents a member's attempt at a written test.
- **Fields:** member (FK), template (FK), started_at, completed_at, score, passed

## WrittenTestAnswer
- **Purpose:** Stores a member's answer to a question in an attempt.
- **Fields:** attempt (FK), question (FK), answer, is_correct

## WrittenTestAssignment
- **Purpose:** Assigns a written test to a member.
- **Fields:** member (FK), template (FK), assigned_by, assigned_at, due_date, completed_at, status

---

## Also See
- [README (App Overview)](README.md)
- [Forms](forms.md)
- [Views](views.md)
- [Management Commands](management.md)
