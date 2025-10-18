from django.conf import settings
from django.contrib.auth.models import Group
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import MaintenanceIssue


@receiver(post_save, sender=MaintenanceIssue)
def notify_meisters_on_issue(sender, instance, created, **kwargs):
    if not created or instance.resolved:
        return
    # Only notify for oil/100hr/annual issues (simple keyword match)
    keywords = ["oil change", "100-hour", "annual"]
    if not any(k in (instance.description or "").lower() for k in keywords):
        return
    # Get all users in the "Meisters" group
    try:
        group = Group.objects.get(name="Meisters")
        recipients = list(group.user_set.values_list("email", flat=True))
    except Group.DoesNotExist:
        recipients = []
    recipients = [e for e in recipients if e]
    if not recipients:
        return
    subject = f"Maintenance Alert: {instance}"
    body = f"A maintenance issue has been created for {instance.glider or instance.towplane}:\n\n{instance.description}\n\nGrounded: {'Yes' if instance.grounded else 'No'}\nLogsheet: {instance.logsheet}\n"
    send_mail(
        subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True
    )
