# Django Management Command Testing Guide

## Overview
This document outlines testing strategies for Django management commands, specifically for CronJob commands in the Manage2Soar project.

## Core Testing Patterns

### 1. Using call_command()
Django provides `call_command()` to programmatically execute management commands in tests:

```python
from django.core.management import call_command
from django.test import TestCase
from io import StringIO

class MyCommandTest(TestCase):
    def test_command_execution(self):
        out = StringIO()
        err = StringIO()

        call_command(
            'my_command',
            '--verbosity=2',
            stdout=out,
            stderr=err
        )

        self.assertIn('Expected output', out.getvalue())
        self.assertEqual('', err.getvalue())  # No errors
```

### 2. Testing CronJob Commands
For our `BaseCronJobCommand` subclasses, we need to test:
- Lock acquisition/release
- Dry run functionality  
- Database operations
- Email sending
- Error handling

### 3. Mocking External Dependencies
Use `unittest.mock` for:
- Email sending (`django.core.mail.send_mail`)
- Time-sensitive operations (`django.utils.timezone.now`)
- Database queries (when needed)

```python
from unittest.mock import patch, MagicMock
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

class CronJobCommandTest(TransactionTestCase):
    """Use TransactionTestCase for database locking tests"""

    @patch('django.core.mail.send_mail')
    def test_sends_email(self, mock_send_mail):
        call_command('my_cronjob_command')
        mock_send_mail.assert_called_once()

    @patch('django.utils.timezone.now')
    def test_time_sensitive_logic(self, mock_now):
        from datetime import datetime
        mock_now.return_value = datetime(2023, 1, 1, 12, 0, 0)
        # Test logic that depends on current time
```

### 4. Database Testing Strategies
For commands that modify data:

```python
class DatabaseCommandTest(TransactionTestCase):
    def setUp(self):
        # Create test data
        self.member = Member.objects.create(
            username="testuser",
            first_name="Test",
            last_name="User"
        )

    def test_command_modifies_data(self):
        initial_count = MyModel.objects.count()
        call_command('my_command')
        final_count = MyModel.objects.count()
        self.assertNotEqual(initial_count, final_count)
```

### 5. Testing Output and Logging

```python
def test_command_output(self):
    out = StringIO()
    call_command('my_command', '--verbosity=2', stdout=out)

    output = out.getvalue()
    self.assertIn('✅', output)  # Success messages
    self.assertIn('🚀', output)  # Start messages
    self.assertIn('Expected log message', output)
```

### 6. Testing Command Arguments

```python
def test_dry_run_option(self):
    with patch('myapp.models.MyModel.objects.create') as mock_create:
        call_command('my_command', '--dry-run')
        mock_create.assert_not_called()

def test_force_option(self):
    # Test that --force bypasses lock acquisition
    with patch('utils.models.CronJobLock.objects.create'):
        call_command('my_command', '--force')
        # Should execute even without lock
```

### 7. Testing Distributed Locking

```python
from utils.models import CronJobLock
from django.db import IntegrityError

class LockingTest(TransactionTestCase):
    def test_lock_prevents_concurrent_execution(self):
        # Create an existing lock
        CronJobLock.objects.create(
            job_name="test_job",
            locked_by="other-pod",
            expires_at=timezone.now() + timedelta(hours=1)
        )

        out = StringIO()
        call_command('my_cronjob_command', stdout=out)

        # Should exit without executing
        self.assertIn('already running', out.getvalue())

    def test_expired_lock_is_replaced(self):
        # Create an expired lock
        CronJobLock.objects.create(
            job_name="test_job",
            locked_by="old-pod",
            expires_at=timezone.now() - timedelta(hours=1)
        )

        call_command('my_cronjob_command')

        # Lock should be updated with new pod
        lock = CronJobLock.objects.get(job_name="test_job")
        self.assertNotEqual(lock.locked_by, "old-pod")
```

## Test Organization Strategy

### File Structure
```
app/
├── management/
│   └── commands/
│       ├── my_command.py
│       └── another_command.py
├── tests/
│   ├── __init__.py
│   ├── test_commands.py          # All command tests
│   ├── test_my_command.py        # Specific command tests
│   └── test_cronjob_base.py      # Base class tests
└── models.py
```

### Test Class Naming
- `Test{CommandName}Command` - for specific commands
- `TestCronJobBase` - for base class functionality
- `Test{Feature}` - for specific features

### Test Method Naming
- `test_{command_name}_{scenario}`
- `test_lock_acquisition_success`
- `test_dry_run_mode`
- `test_email_sending`

## Mock Patterns for Common Operations

### Email Mocking
```python
@patch('django.core.mail.send_mail')
def test_email_content(self, mock_send_mail):
    call_command('notify_command')

    args, kwargs = mock_send_mail.call_args
    self.assertEqual(kwargs['subject'], 'Expected Subject')
    self.assertIn('Expected content', kwargs['message'])
    self.assertEqual(kwargs['recipient_list'], ['test@example.com'])
```

### Timezone Mocking
```python
@patch('django.utils.timezone.now')
def test_time_based_logic(self, mock_now):
    test_date = datetime(2023, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    mock_now.return_value = test_date

    call_command('time_sensitive_command')
    # Test logic that depends on specific dates
```

### Database Query Mocking (when needed)
```python
@patch('myapp.models.MyModel.objects.filter')
def test_query_logic(self, mock_filter):
    mock_filter.return_value.count.return_value = 5

    out = StringIO()
    call_command('my_command', stdout=out)

    self.assertIn('Found 5 items', out.getvalue())
```

## Integration Testing Approach

### Full Command Execution Tests
```python
class IntegrationTest(TransactionTestCase):
    def setUp(self):
        # Create realistic test data
        self.create_test_members()
        self.create_test_logsheets()

    def test_full_command_execution(self):
        """Test command with real database operations"""
        call_command('aging_logsheet_command')

        # Verify expected database changes
        # Verify emails were queued/sent
        # Verify logs were created
```

## Specific Test Requirements for Our Commands

### 1. Aging Logsheet Command Tests
- Test detection of 7+ day old unfinalized logsheets
- Test duty officer notification
- Test dry run mode
- Test empty result set

### 2. Late SPR Command Tests  
- Test 7/14/21/25/30 day intervals
- Test escalating notification content
- Test instructor identification
- Test multiple overdue reports per instructor

### 3. Duty Delinquent Command Tests
- Test active member identification
- Test duty participation history
- Test 3+ month membership requirement
- Test monthly report generation

### 4. Lock Management Tests
- Test concurrent execution prevention
- Test lock expiration handling
- Test graceful failure on lock conflicts
- Test lock cleanup

## Running Tests

```bash
# Run all command tests
python manage.py test --pattern="test_*command*"

# Run specific command tests
python manage.py test app.tests.test_my_command

# Run with coverage
pytest --cov=utils.management.commands --cov=app.management.commands

# Run integration tests
python manage.py test --tag=integration
```

## Best Practices

1. **Use TransactionTestCase** for locking tests (need real DB transactions)
2. **Use TestCase** for logic-only tests (faster)
3. **Mock external services** (email, APIs)
4. **Test both success and failure scenarios**
5. **Test command-line arguments** and options
6. **Verify output messages** for user feedback
7. **Test with realistic data** in integration tests
8. **Clean up locks** in test tearDown methods

---

This testing framework will ensure our CronJob commands are reliable, well-tested, and maintainable.
