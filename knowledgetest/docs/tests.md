# Knowledge Test Testing Documentation

This document describes the test suite for the `knowledgetest` Django app, including all test classes, their purpose, and what functionality they cover.

---

## Test Files

### `test_quiz_flow.py`

The main test file containing comprehensive tests for written test functionality, including the core quiz flow, notifications, instruction report integration, and administrative features.

---

## Test Classes

### QuizFlowTests

Tests the core written test submission and completion workflow.

#### Core Functionality Tests

- **`test_student_submission_records_attempt_and_scores`**
  - Simulates a complete student test submission
  - Verifies attempt recording, score calculation (50%), and pass/fail logic
  - Checks that individual answer records are created correctly

- **`test_start_view_renders_questions`**
  - Tests the quiz start view renders properly with question context
  - Verifies assignment permissions and question data structure

- **`test_submit_creates_attempt_and_answers`**
  - Tests the submission process creates WrittenTestAttempt and WrittenTestAnswer records
  - Validates score calculation and pass threshold logic

- **`test_invalid_payload_returns_error`**
  - Tests malformed JSON submission handling
  - Ensures proper error display without crashing

#### Integration Tests

- **`test_completion_creates_notifications_for_instructor`**
  - Tests notification creation for instructors when students complete tests
  - Verifies instructor and test creator notification logic
  - Validates notification message content

- **`test_completion_creates_instruction_report_with_persistent_link`** ⭐ *New*
  - Tests InstructionReport creation with embedded result links
  - Validates persistent access to test results even after notification dismissal
  - Verifies report content includes score, status, and clickable link
  - Ensures correct URL generation for test attempt results

### WrittenTestDeleteTests ⭐ *New Test Class*

Comprehensive test suite for the written test attempt deletion functionality, covering permission-based access control and data integrity.

#### Permission Tests

- **`test_staff_can_delete_attempt`**
  - Verifies staff users can delete any written test attempt
  - Tests proper redirect to student instruction record after deletion

- **`test_instructor_can_delete_own_attempt`**
  - Tests that grading instructors can delete attempts they graded
  - Validates instructor-specific permissions

- **`test_template_creator_can_delete_attempt`**
  - Verifies test creators/proctors can delete attempts from their templates
  - Tests scenario where template creator differs from grading instructor

#### Security Tests

- **`test_unauthorized_user_cannot_delete_attempt`**
  - Ensures users without proper permissions receive 403 Forbidden
  - Tests that unauthorized deletion attempts don't affect data

- **`test_student_cannot_delete_own_attempt`**
  - Verifies students cannot delete their own test attempts
  - Confirms student permission boundaries

#### HTTP Method & Error Handling Tests

- **`test_get_request_not_allowed`**
  - Ensures only POST requests are allowed for deletion
  - Tests proper 405 Method Not Allowed response

- **`test_delete_nonexistent_attempt_returns_404`**
  - Tests 404 handling for attempts that don't exist
  - Validates proper error responses

#### Data Integrity Tests

- **`test_delete_removes_related_answers`**
  - Verifies cascade deletion of WrittenTestAnswer records
  - Tests database relationship integrity during deletion

#### UI/UX Tests ⭐ *New*

- **`test_result_page_shows_delete_button_with_confirmation`**
  - Verifies delete button is present for authorized users
  - Tests JavaScript confirmation dialog is properly configured
  - Validates button text and confirmation message content
  - Ensures form action points to correct delete URL

- **`test_result_page_shows_pass_threshold`**
  - Tests that result page displays both score and required pass percentage
  - Verifies students can see what percentage was needed to pass
  - Addresses UX issue where failed students didn't know the pass threshold

---

## Recent Additions (Issue #176 UX Improvements)

The test suite was expanded to support new UX improvements for written test results:

### Persistent Result Access
- **New Test**: `test_completion_creates_instruction_report_with_persistent_link`
- **Purpose**: Ensures test results remain accessible through InstructionReport even after notifications are dismissed
- **Implementation**: Validates that InstructionReport.report_text contains an HTML link to the test result

### Administrative Deletion Features
- **New Test Class**: `WrittenTestDeleteTests` (8 comprehensive tests)
- **Purpose**: Complete coverage of the new deletion functionality for instructors and staff
- **Security Model**: 
  - Staff can delete any attempt
  - Grading instructors can delete attempts they graded
  - Template creators can delete attempts from their tests
  - Students and unauthorized users cannot delete attempts

### Enhanced Permission Testing
- **Multi-user Setup**: Tests create student, instructor, staff, and unauthorized user accounts
- **Role-based Access**: Each test validates specific permission boundaries
- **HTTP Security**: Tests validate proper HTTP methods and status codes

---

## Test Data Setup

### QuizFlowTests Setup
- Creates student with "Student Member" status
- Creates test category "PRE" (Pre-solo)
- Creates 2 questions with known correct answers
- Creates template with 50% pass threshold
- Sets up assignment relationship between student and test

### WrittenTestDeleteTests Setup
- Creates multiple user types (student, instructor, staff, other)
- Sets appropriate membership_status for each user
- Creates test content (category, question, template)
- Creates attempt with answer record for deletion testing
- Establishes proper relationship hierarchy for permission testing

---

## Running Tests

```bash
# Run all knowledgetest tests
python -m pytest knowledgetest/test_quiz_flow.py -v

# Run specific test class
python -m pytest knowledgetest/test_quiz_flow.py::QuizFlowTests -v
python -m pytest knowledgetest/test_quiz_flow.py::WrittenTestDeleteTests -v

# Run specific test
python -m pytest knowledgetest/test_quiz_flow.py::WrittenTestDeleteTests::test_staff_can_delete_attempt -v
```

---

## Test Coverage Areas

### ✅ Covered Functionality
- Quiz submission and scoring
- Notification creation
- InstructionReport integration with persistent links
- Permission-based deletion with security boundaries
- HTTP method validation
- Error handling (404, 403, 405)
- Database integrity and cascade deletion

### 🔄 Integration Points Tested
- User authentication and membership status
- Cross-app model relationships (InstructionReport, Notification)
- URL routing and reverse URL generation
- Template and view integration

### 🛡️ Security Aspects Tested
- Authentication requirements
- Permission-based access control
- HTTP method restrictions
- Unauthorized access prevention
- Data integrity during operations

---

## Notes for Contributors

- All tests use proper Django TestCase patterns with database transactions
- Tests include type safety with `cast()` for mypy compliance
- Comprehensive assertion messages help with debugging failures
- Test data is isolated per test class to prevent interference
- Permission tests cover all user role combinations
- Error handling tests ensure graceful failure modes

The test suite provides robust coverage for both the core functionality and new administrative features, ensuring reliable operation across different user roles and scenarios.