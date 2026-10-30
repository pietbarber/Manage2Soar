"""
Signals for member-related notifications.
Notifies membership managers about important member events.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.url_helpers import build_absolute_url, get_canonical_url

from .models import (
    Member,
    MemberRoleAssignment,
    MemberRoleAssignmentEvent,
    RoleMetadata,
)
from .role_audit import get_actor

logger = logging.getLogger(__name__)


def _deleting_model(origin):
    """Return the top-level model being deleted, when Django provides it."""
    if isinstance(origin, models.Model):
        return type(origin)
    return getattr(origin, "model", None)


def _assignment_identity(instance, using):
    """Read canonical identity for an assignment before it is removed.

    Django sends ``pre_delete`` for every object in a deletion plan before
    deleting any of them, so this snapshot still sees the Member, Group, and
    RoleMetadata rows even during a cascade.
    """
    return {
        "member_username": (
            Member.objects.using(using)
            .filter(pk=instance.member_id)
            .values_list("username", flat=True)
            .first()
            or ""
        ),
        "group_name": (
            Group.objects.using(using)
            .filter(pk=instance.group_id)
            .values_list("name", flat=True)
            .first()
            or ""
        ),
        "role_key": (
            RoleMetadata.objects.using(using)
            .filter(group_id=instance.group_id)
            .values_list("key", flat=True)
            .first()
            or ""
        ),
    }


@receiver(pre_delete, sender=MemberRoleAssignment)
def snapshot_deleted_role_assignment(sender, instance, using, **kwargs):
    """Capture related identity before a cascade deletes it.

    Without this, a Group cascade can remove RoleMetadata before the
    assignment's post-delete signal runs, losing the stable ``role_key`` from
    the revoke event exactly when the historical record matters most.
    """
    snapshot = _assignment_identity(instance, using)
    instance._audit_member_username = snapshot["member_username"]
    instance._audit_group_name = snapshot["group_name"]
    instance._audit_role_key = snapshot["role_key"]


@receiver(post_save, sender=MemberRoleAssignment)
def record_created_role_assignment(sender, instance, created, using, **kwargs):
    """Append a grant event for every assignment creation.

    This is the model-level backstop for direct ORM creation.  The supported
    service path sets :func:`members.role_audit.actor_scope`, so it records the
    administrator; an uncovered direct write is recorded as a system grant
    unless the assignment itself names an actor.  Updates are rejected by the
    model, and bulk creation is rejected by its manager, so create is the only
    uncovered mutation path.
    """
    if not created or kwargs.get("raw"):
        # Fixture loads create historical rows, not live administrative
        # actions; do not manufacture audit events for them.
        return

    using = using or instance._state.db
    snapshot = _assignment_identity(instance, using)
    actor = get_actor()
    if actor is None and instance.actor_id is not None:
        actor = Member.objects.using(using).filter(pk=instance.actor_id).first()
    actor_id = actor.pk if actor is not None and actor.pk is not None else None
    actor_username = ""
    if actor_id is not None:
        actor_username = Member.objects.using(using).filter(pk=actor_id).values_list(
            "username", flat=True
        ).first() or (actor.get_username() if actor is not None else "")

    MemberRoleAssignmentEvent.objects.using(using).create(
        member_id=instance.member_id,
        member_id_snapshot=instance.member_id,
        member_username=snapshot["member_username"],
        group_id=instance.group_id,
        group_id_snapshot=instance.group_id,
        group_name=snapshot["group_name"],
        role_key=snapshot["role_key"],
        action="grant",
        actor_id=actor_id,
        actor_id_snapshot=actor_id,
        actor_username=actor_username,
        source=instance.source,
        source_key=instance.source_key,
    )


@receiver(post_delete, sender=MemberRoleAssignment)
def record_deleted_role_assignment(sender, instance, using, **kwargs):
    """Append a revoke event for every assignment deletion, including cascades.

    Assignment rows are provenance, not the audit ledger.  The ledger keeps
    snapshot identity so it survives the deletion that triggered it.  When a
    Member or Group cascade is in progress, the convenience foreign keys are
    left null: the parent row is about to disappear, and Django has already
    planned its SET_NULL updates before this new event row exists.
    """
    origin = kwargs.get("origin")
    deleting_model = _deleting_model(origin)
    deleting_origin_unknown = deleting_model is None

    member_id = instance.member_id
    group_id = instance.group_id
    actor = get_actor()
    actor_id = actor.pk if actor is not None and actor.pk is not None else None
    actor_id_snapshot = actor_id

    if deleting_model is Member:
        member_id = None
        # The actor may be a different Member in the same delete set.  Django
        # cannot know that here, and a live FK to a row that is also being
        # deleted aborts the cascade.  The snapshot fields retain attribution.
        actor_id = None
    elif deleting_model is Group:
        group_id = None
    elif deleting_origin_unknown:
        # Conservatively avoid an FK to a parent whose delete ordering is
        # unknown; the snapshot fields still carry the complete identity.
        member_id = None
        group_id = None
        actor_id = None

    if hasattr(instance, "_audit_role_key"):
        member_username = instance._audit_member_username
        group_name = instance._audit_group_name
        role_key = instance._audit_role_key
    else:
        snapshot = _assignment_identity(instance, using)
        member_username = snapshot["member_username"]
        group_name = snapshot["group_name"]
        role_key = snapshot["role_key"]

    actor_username = ""
    if actor_id_snapshot is not None:
        actor_username = Member.objects.using(using).filter(
            pk=actor_id_snapshot
        ).values_list("username", flat=True).first() or (
            actor.get_username() if actor is not None else ""
        )

    MemberRoleAssignmentEvent.objects.using(using).create(
        member_id=member_id,
        member_id_snapshot=instance.member_id,
        member_username=member_username,
        group_id=group_id,
        group_id_snapshot=instance.group_id,
        group_name=group_name,
        role_key=role_key,
        action="revoke",
        actor_id=actor_id,
        actor_id_snapshot=actor_id_snapshot,
        actor_username=actor_username,
        source=instance.source,
        source_key=instance.source_key,
    )


def _membership_application_email_urls(application, site_url):
    review_path = reverse(
        "members:membership_application_detail",
        args=[application.application_id],
    )
    list_path = reverse("members:membership_applications_list")
    return {
        "review_application_url": build_absolute_url(review_path, canonical=site_url),
        "all_applications_url": build_absolute_url(list_path, canonical=site_url),
    }


def _create_notification_if_not_exists(user, message, url=None):
    """Create notification if similar one doesn't already exist (dedupe)."""
    try:
        from notifications.models import Notification

        # Check if we already have an undismissed notification for this user
        # with the same message to prevent spam
        existing = Notification.objects.filter(
            user=user, dismissed=False, message=message
        ).exists()
        if existing:
            logger.debug(
                "Notification suppressed (duplicate) for user=%s, message=%s",
                getattr(user, "pk", None),
                message[:50],
            )
            return None

        return Notification.objects.create(user=user, message=message, url=url)
    except ImportError:
        # Notifications app not available
        return None


def _notify_member_managers_of_visiting_pilot(member, returning=False):
    """
    Send notifications to member managers about a visiting pilot registration or check-in.
    Based on the membership manager workflow requirements.
    """
    try:
        # Get site configuration
        config = SiteConfiguration.objects.first()
        if not config:
            logger.error("SiteConfiguration not found - cannot send notifications")
            return

        # Get all member managers
        member_managers = Member.objects.filter(member_manager=True, is_active=True)

        if not member_managers.exists():
            # Fallback to webmasters if no member managers
            member_managers = Member.objects.filter(webmaster=True, is_active=True)

        if not member_managers.exists():
            logger.warning(
                "No member managers or webmasters found for visiting pilot notification"
            )
            return

        # Prepare notification content
        auto_approved = getattr(config, "visiting_pilot_auto_approve", False)
        status_text = "activated" if auto_approved else "pending approval"

        # Email notification (if email is configured)
        if hasattr(settings, "DEFAULT_FROM_EMAIL") and settings.DEFAULT_FROM_EMAIL:
            try:
                # Sanitize all user input for email content
                safe_name = f"{member.first_name} {member.last_name}".replace(
                    "\r", ""
                ).replace("\n", " ")
                safe_email = member.email.replace("\r", "").replace("\n", " ")
                safe_home_club = (
                    (member.home_club or "Unknown Club")
                    .replace("\r", "")
                    .replace("\n", " ")
                )
                safe_ssa = (
                    (member.SSA_member_number or "Not provided")
                    .replace("\r", "")
                    .replace("\n", " ")
                )

                if returning:
                    subject = f"Visiting Pilot Check-In: {safe_name[:50]}"
                else:
                    subject = f"New Visiting Pilot Registration: {safe_name[:50]}"

                # Prepare context for email templates - compute canonical once to avoid redundant DB queries
                site_url = get_canonical_url()
                context = {
                    "member": member,
                    "auto_approved": auto_approved,
                    "status_text": status_text,
                    "glider_rating": member.get_glider_rating_display()
                    or "Not specified",
                    "registration_time": member.date_joined.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "manage_member_url": build_absolute_url(
                        f"/admin/members/member/{member.pk}/change/", canonical=site_url
                    ),
                    "all_visiting_pilots_url": build_absolute_url(
                        f"/admin/members/member/?membership_status__exact={config.visiting_pilot_status}",
                        canonical=site_url,
                    ),
                    "club_name": config.club_name if config else "Club",
                    "club_logo_url": get_absolute_club_logo_url(config),
                    "site_url": site_url,
                }

                # Render HTML and plain text templates
                html_message = render_to_string(
                    "members/emails/visiting_pilot_notification.html", context
                )
                text_message = render_to_string(
                    "members/emails/visiting_pilot_notification.txt", context
                )

                # Send email to each member manager
                recipient_emails = [
                    manager.email for manager in member_managers if manager.email
                ]

                if recipient_emails:
                    send_mail(
                        subject=subject,
                        message=text_message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        html_message=html_message,
                        fail_silently=False,  # We want to know if email fails
                    )

            except Exception as e:
                # Log the error but don't fail the registration
                logger.error(f"Failed to send visiting pilot notification email: {e}")

        # In-app notifications
        try:
            action_text = "checked in again" if returning else "registered"
            notification_message = (
                f"Visiting pilot {action_text}: {member.first_name} {member.last_name} "
                f"({member.home_club or 'Unknown Club'}) - {status_text}"
            )

            try:
                notification_url = reverse(
                    "admin:members_member_change", args=[member.pk]
                )
            except Exception:
                notification_url = None

            for manager in member_managers:
                _create_notification_if_not_exists(
                    manager, notification_message, url=notification_url
                )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create visiting pilot notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the registration
        logger.error(
            f"Failed to notify member managers of visiting pilot registration: {e}"
        )


@receiver(post_save, sender=Member)
def notify_member_managers_of_visiting_pilot(sender, instance, created, **kwargs):
    """
    Signal handler that notifies member managers when a visiting pilot registers.

    This signal is triggered on Member post_save to check if a new visiting pilot
    has registered and needs approval notifications sent to member managers.
    """

    if not created:
        return  # Only notify on creation, not updates

    try:
        # Check if this is a visiting pilot by checking membership status
        config = SiteConfiguration.objects.first()
        if not config or not config.visiting_pilot_enabled:
            return

        # Check if this member is a visiting pilot
        if (
            hasattr(config, "visiting_pilot_status")
            and config.visiting_pilot_status
            and instance.membership_status == config.visiting_pilot_status
        ):
            logger.info(
                f"New visiting pilot detected: {instance.email} ({instance.first_name} {instance.last_name})"
            )
            _notify_member_managers_of_visiting_pilot(instance)

    except Exception as e:
        # Log the error but don't fail the member creation
        logger.error(f"Failed to process visiting pilot notification signal: {e}")


def notify_membership_managers_of_new_application(application):
    """
    Send notifications to membership managers about new membership application.
    Called directly from views when a new application is submitted.
    """
    try:
        # Get site configuration
        config = SiteConfiguration.objects.first()
        if not config:
            logger.error("SiteConfiguration not found - cannot send notifications")
            return

        # Get all member managers
        member_managers = Member.objects.filter(member_manager=True, is_active=True)

        if not member_managers.exists():
            # Fallback to webmasters if no member managers
            member_managers = Member.objects.filter(webmaster=True, is_active=True)

        if not member_managers.exists():
            logger.warning(
                "No member managers or webmasters found for membership application notification"
            )
            return

        # Email notification (if email is configured)
        if hasattr(settings, "DEFAULT_FROM_EMAIL") and settings.DEFAULT_FROM_EMAIL:
            try:
                # Sanitize all user input for email content
                safe_name = f"{application.first_name} {application.last_name}".replace(
                    "\r", ""
                ).replace("\n", " ")
                safe_email = application.email.replace("\r", "").replace("\n", " ")
                safe_phone = (
                    (application.phone or "Not provided")
                    .replace("\r", "")
                    .replace("\n", " ")
                )
                safe_city = f"{application.city}, {application.state}".replace(
                    "\r", ""
                ).replace("\n", " ")

                subject = f"New Membership Application: {safe_name[:50]}"

                # Prepare context for email templates
                # Compute canonical URL once to avoid redundant DB queries
                site_url = get_canonical_url()
                context = {
                    "application": application,
                    "submitted_at": application.submitted_at.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "club_name": config.club_name if config else "Club",
                    "club_logo_url": get_absolute_club_logo_url(config),
                    "site_url": site_url,
                    **_membership_application_email_urls(application, site_url),
                }

                # Render HTML and plain text templates
                html_message = render_to_string(
                    "members/emails/application_submitted.html", context
                )
                text_message = render_to_string(
                    "members/emails/application_submitted.txt", context
                )

                # Send email to each member manager
                recipient_emails = [
                    manager.email for manager in member_managers if manager.email
                ]

                if recipient_emails:
                    send_mail(
                        subject=subject,
                        message=text_message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        html_message=html_message,
                        fail_silently=False,  # We want to know if email fails
                    )

            except Exception as e:
                # Log the error but don't fail the application submission
                logger.error(
                    f"Failed to send membership application notification email: {e}"
                )

        # In-app notifications
        try:
            notification_message = (
                f"New membership application: {application.first_name} {application.last_name} "
                f"({application.city}, {application.state}) - pending review"
            )

            try:
                notification_url = reverse(
                    "members:membership_application_detail",
                    args=[application.application_id],
                )
            except Exception:
                notification_url = None

            for manager in member_managers:
                _create_notification_if_not_exists(
                    manager, notification_message, url=notification_url
                )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create membership application notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the application submission
        logger.error(f"Failed to notify member managers of membership application: {e}")


def notify_membership_managers_of_application(application):
    """
    Send notifications to membership managers about new membership applications.
    Called directly from views when an application is submitted.

    Args:
        application (MembershipApplication): The application that was submitted
    """
    try:
        # Get site configuration
        config = SiteConfiguration.objects.first()
        if not config:
            logger.error("SiteConfiguration not found - cannot send notifications")
            return

        # Get all member managers
        member_managers = Member.objects.filter(member_manager=True, is_active=True)

        if not member_managers.exists():
            # Fallback to webmasters if no member managers
            member_managers = Member.objects.filter(webmaster=True, is_active=True)

        if not member_managers.exists():
            logger.warning(
                "No member managers or webmasters found for membership application notification"
            )
            return

        # Email notification (if email is configured)
        if hasattr(settings, "DEFAULT_FROM_EMAIL") and settings.DEFAULT_FROM_EMAIL:
            try:
                # Sanitize all user input for email content
                safe_name = f"{application.first_name} {application.last_name}".replace(
                    "\r", ""
                ).replace("\n", " ")
                subject = f"New Membership Application: {safe_name[:50]}"

                site_url = get_canonical_url()
                context = {
                    "application": application,
                    "submitted_at": application.submitted_at.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "club_name": config.club_name if config else "Club",
                    "club_logo_url": get_absolute_club_logo_url(config),
                    "site_url": site_url,
                    **_membership_application_email_urls(application, site_url),
                }

                html_message = render_to_string(
                    "members/emails/application_submitted.html", context
                )
                text_message = render_to_string(
                    "members/emails/application_submitted.txt", context
                )

                # Send email to each member manager
                recipient_emails = [
                    manager.email for manager in member_managers if manager.email
                ]

                if recipient_emails:
                    send_mail(
                        subject=subject,
                        message=text_message,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        recipient_list=recipient_emails,
                        html_message=html_message,
                        fail_silently=False,  # We want to know if email fails
                    )

            except Exception as e:
                # Log the error but don't fail the application submission
                logger.error(
                    f"Failed to send membership application notification email: {e}"
                )

        # In-app notifications
        try:
            notification_message = (
                f"New membership application from {application.first_name} {application.last_name} "
                f"({application.email}) - ID: {application.application_id}"
            )

            try:
                notification_url = reverse(
                    "members:membership_application_detail",
                    args=[application.application_id],
                )
            except Exception:
                notification_url = None

            for manager in member_managers:
                _create_notification_if_not_exists(
                    manager, notification_message, url=notification_url
                )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create membership application notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the application submission
        logger.error(f"Failed to notify member managers of membership application: {e}")


def notify_membership_managers_of_withdrawal(application):
    """
    Send notifications to membership managers when an applicant withdraws their application.

    Args:
        application (MembershipApplication): The application that was withdrawn
    """
    try:
        # Get site configuration
        config = SiteConfiguration.objects.first()
        if not config:
            logger.error(
                "SiteConfiguration not found - cannot send withdrawal notifications"
            )
            return

        # Get all member managers
        member_managers = Member.objects.filter(member_manager=True, is_active=True)

        if not member_managers.exists():
            # Fallback to webmasters if no member managers
            member_managers = Member.objects.filter(webmaster=True, is_active=True)

        if not member_managers.exists():
            logger.warning(
                "No member managers or webmasters found for application withdrawal notification"
            )
            return

        # Email notification (if email is configured)
        if hasattr(settings, "DEFAULT_FROM_EMAIL") and settings.DEFAULT_FROM_EMAIL:
            try:
                # Sanitize all user input for email content
                safe_name = f"{application.first_name} {application.last_name}".replace(
                    "\r", ""
                ).replace("\n", " ")
                safe_email = application.email.replace("\r", "").replace("\n", " ")

                subject = f"Membership Application Withdrawn: {safe_name[:50]}"

                # Prepare context for email templates
                site_url = get_canonical_url()
                context = {
                    "application": application,
                    "submitted_at": application.submitted_at.strftime(
                        "%B %d, %Y at %I:%M %p"
                    ),
                    "view_application_url": build_absolute_url(
                        f"/members/applications/{application.application_id}/",
                        canonical=site_url,
                    ),
                    "club_name": config.club_name if config else "Club",
                    "club_logo_url": get_absolute_club_logo_url(config),
                    "site_url": site_url,
                }

                # Render HTML and plain text templates
                html_message = render_to_string(
                    "members/emails/application_withdrawn.html", context
                )
                text_message = render_to_string(
                    "members/emails/application_withdrawn.txt", context
                )

                # Send email to all member managers
                for manager in member_managers:
                    if manager.email:
                        try:
                            send_mail(
                                subject=subject,
                                message=text_message,
                                from_email=settings.DEFAULT_FROM_EMAIL,
                                recipient_list=[manager.email],
                                html_message=html_message,
                                fail_silently=False,
                            )
                            logger.info(
                                f"Sent withdrawal notification to {manager.email} for application {application.application_id}"
                            )
                        except Exception as email_error:
                            logger.error(
                                f"Failed to send withdrawal notification email to {manager.email}: {email_error}"
                            )

                logger.info(
                    f"Processed withdrawal notifications for application {application.application_id}"
                )

            except Exception as e:
                logger.error(f"Failed to send withdrawal notification emails: {e}")

        # In-app notification
        try:
            from notifications.models import Notification

            notification_message = (
                f"Membership application withdrawn: {safe_name} ({safe_email})"
            )

            for manager in member_managers:
                Notification.objects.create(
                    recipient=manager,
                    notification_type="membership_application_withdrawn",
                    title="Membership Application Withdrawn",
                    message=notification_message,
                    related_object_type="membership_application",
                    related_object_id=str(application.application_id),
                    priority="medium",
                )

            logger.info(
                f"Created in-app withdrawal notifications for application {application.application_id}"
            )

        except Exception as e:
            # Log but don't fail
            logger.error(f"Failed to create withdrawal notifications: {e}")

    except Exception as e:
        # Log the error but don't fail the withdrawal process
        logger.error(f"Failed to notify member managers of application withdrawal: {e}")
