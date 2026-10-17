import pytest


@pytest.fixture(autouse=True)
def disable_email_dev_mode_for_member_tests(settings):
    """Keep local EMAIL_DEV_MODE environment settings out of member tests."""
    settings.EMAIL_DEV_MODE = False
    settings.EMAIL_DEV_MODE_REDIRECT_TO = ""
