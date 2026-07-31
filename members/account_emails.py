import math

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from siteconfig.models import SiteConfiguration
from utils.email import enforce_noreply_from_email
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url


def send_account_setup_email(member):
    """Send a direct account invitation with a one-time password setup link."""
    if member.pk is None:
        raise ValueError("The member must be saved before sending an account email.")
    if not member.email:
        raise ValueError("The member must have an email address.")

    uidb64 = urlsafe_base64_encode(force_bytes(member.pk))
    token = default_token_generator.make_token(member)
    setup_path = reverse(
        "password_reset_confirm",
        kwargs={"uidb64": uidb64, "token": token},
    )
    setup_url = build_absolute_url(setup_path, canonical=get_canonical_url())
    config = SiteConfiguration.objects.first()
    timeout_hours = math.ceil(settings.PASSWORD_RESET_TIMEOUT / 3600)
    context = {
        "club_name": config.club_name if config else "Manage2Soar",
        "club_logo_url": get_absolute_club_logo_url(config) if config else "",
        "member": member,
        "password_reset_timeout_hours": timeout_hours,
        "setup_url": setup_url,
    }

    subject = render_to_string(
        "members/emails/account_created_subject.txt", context
    ).strip()
    subject = "".join(subject.splitlines())
    text_message = render_to_string("members/emails/account_created.txt", context)
    html_message = render_to_string("members/emails/account_created.html", context)

    from utils.email import DevModeEmailMultiAlternatives

    message = DevModeEmailMultiAlternatives(
        subject=subject,
        body=text_message,
        from_email=enforce_noreply_from_email(settings.DEFAULT_FROM_EMAIL),
        to=[member.email],
    )
    message.attach_alternative(html_message, "text/html")
    return message.send()
