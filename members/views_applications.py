import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from siteconfig.models import SiteConfiguration

from .decorators import active_member_required
from .forms_applications import (
    MembershipApplicationForm,
    MembershipApplicationReviewForm,
)
from .models_applications import MembershipApplication

logger = logging.getLogger(__name__)


@ensure_csrf_cookie
@require_http_methods(["GET", "POST"])
def membership_application(request):
    """
    Public membership application form for non-logged-in users.

    Per Issue #245 requirements:
    - Must be available to users who are NOT logged in
    - Must NOT work if user IS logged in
    """

    # Check if user is logged in - reject if they are
    if request.user.is_authenticated:
        messages.error(
            request,
            "You are already logged in. If you need to update your membership information, "
            "please use your member profile or contact our membership managers.",
        )
        return redirect("home")

    # Get site configuration
    config = SiteConfiguration.objects.first()
    if not config or not config.membership_application_enabled:
        messages.error(
            request,
            "Membership applications are currently not available. "
            "Please contact us directly for membership information.",
        )
        return redirect("home")

    if request.method == "POST":
        form = MembershipApplicationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create the application
                    application = form.save(commit=False)
                    application.status = "pending"
                    application.save()

                    logger.info(
                        f"New membership application submitted: {application.email} "
                        f"({application.first_name} {application.last_name}) - ID: {application.application_id}"
                    )

                    # Trigger notification to membership managers
                    # Import here to avoid circular imports
                    from .signals import notify_membership_managers_of_new_application

                    notify_membership_managers_of_new_application(application)

                    messages.success(
                        request,
                        f"Thank you, {application.first_name}! Your membership application has been submitted successfully. "
                        f"Our membership managers will review your application and contact you within 1-2 business days. "
                        f"Your application ID is: {application.application_id}",
                    )

                    # Redirect to confirmation page with application ID
                    return redirect(
                        "members:membership_application_status",
                        application_id=application.application_id,
                    )

            except Exception as e:
                logger.error(f"Failed to save membership application: {e}")
                messages.error(
                    request,
                    "There was an error processing your application. Please try again or contact us directly.",
                )
        else:
            messages.error(
                request,
                "Please correct the errors below and submit your application again.",
            )
    else:
        # Check for OAuth2 prefill data (Issue #164)
        initial_data = {}
        oauth2_prefill = request.session.get("oauth2_prefill")
        if oauth2_prefill:
            initial_data = {
                "email": oauth2_prefill.get("email", ""),
                "first_name": oauth2_prefill.get("first_name", ""),
                "last_name": oauth2_prefill.get("last_name", ""),
            }

        form = MembershipApplicationForm(initial=initial_data)

    # Check if user came from OAuth2 redirect and clear session data
    from_oauth2 = False
    if "oauth2_prefill" in request.session:
        from_oauth2 = request.session["oauth2_prefill"].get("from_oauth2", False)
        # Clear the session data after use
        del request.session["oauth2_prefill"]

    return render(
        request,
        "members/membership_application.html",
        {
            "form": form,
            "config": config,
            "from_oauth2": from_oauth2,
            "page_title": (
                f"Membership Application - {config.club_name}"
                if config
                else "Membership Application"
            ),
        },
    )


@active_member_required
def membership_applications_list(request):
    """
    List of all membership applications for membership managers.
    Only accessible to members with member_manager role.
    """

    # Check if user has permission to manage memberships
    if not (
        request.user.member_manager
        or request.user.webmaster
        or request.user.is_superuser
    ):
        raise PermissionDenied(
            "You do not have permission to view membership applications."
        )

    # Get filter parameters
    # Default to 'active' instead of 'all'
    status_filter = request.GET.get("status", "active")
    search_query = request.GET.get("q", "").strip()

    # Build queryset
    from django.db import models

    applications = MembershipApplication.objects.select_related(
        "reviewed_by", "member_account"
    )

    if status_filter == "active":
        # Show only applications that need attention (exclude approved/rejected/withdrawn)
        applications = applications.exclude(
            status__in=["approved", "rejected", "withdrawn"]
        )
    elif status_filter != "all":
        applications = applications.filter(status=status_filter)

    if search_query:
        applications = applications.filter(
            models.Q(first_name__icontains=search_query)
            | models.Q(last_name__icontains=search_query)
            | models.Q(email__icontains=search_query)
        )

    # Order applications - pending first, then by submission date
    applications = applications.order_by(
        models.Case(
            models.When(status="pending", then=0),
            models.When(status="under_review", then=1),
            models.When(status="additional_info_needed", then=2),
            models.When(status="waitlisted", then=3),
            default=4,
        ),
        "waitlist_position",  # For waitlisted applications
        "-submitted_at",
    )

    # Get counts for status badges
    status_counts = MembershipApplication.objects.values("status").annotate(
        count=models.Count("id")
    )
    status_counts_dict = {item["status"]: item["count"] for item in status_counts}

    return render(
        request,
        "members/membership_applications_list.html",
        {
            "applications": applications,
            "status_filter": status_filter,
            "search_query": search_query,
            "status_counts": status_counts_dict,
            "status_choices": MembershipApplication.STATUS_CHOICES,
        },
    )


@active_member_required
def membership_application_detail(request, application_id):
    """
    Detailed view of a membership application with review capabilities.
    Only accessible to membership managers.
    """

    # Check permissions
    if not (
        request.user.member_manager
        or request.user.webmaster
        or request.user.is_superuser
    ):
        raise PermissionDenied(
            "You do not have permission to view membership applications."
        )

    # Get the application
    application = get_object_or_404(
        MembershipApplication, application_id=application_id
    )

    if request.method == "POST":
        review_form = MembershipApplicationReviewForm(
            request.POST, instance=application
        )

        # Handle review action
        review_action = request.POST.get("review_action")

        if review_action and review_form.is_valid():
            try:
                with transaction.atomic():
                    application = review_form.save(commit=False)

                    if review_action == "approve":
                        # Approve the application and create member account
                        member = application.approve_application(
                            reviewed_by=request.user
                        )

                        messages.success(
                            request,
                            f"Application approved! Member account created for {application.full_name}. "
                            f"They have been assigned the status '{member.membership_status}'.",
                        )

                        # TODO: Send approval email to applicant
                        logger.info(
                            f"Application {application.application_id} approved by {request.user}"
                        )

                    elif review_action == "waitlist":
                        application.add_to_waitlist(reviewed_by=request.user)
                        messages.success(
                            request,
                            f"Application added to waiting list at position {application.waitlist_position}.",
                        )

                        # TODO: Send waitlist email to applicant
                        logger.info(
                            f"Application {application.application_id} waitlisted by {request.user}"
                        )

                    elif review_action == "reject":
                        application.reject_application(reviewed_by=request.user)
                        messages.success(request, "Application has been rejected.")

                        # TODO: Send rejection email to applicant
                        logger.info(
                            f"Application {application.application_id} rejected by {request.user}"
                        )

                    elif review_action == "need_info":
                        application.status = "additional_info_needed"
                        application.reviewed_by = request.user
                        application.reviewed_at = timezone.now()
                        application.admin_notes = review_form.cleaned_data.get(
                            "admin_notes", ""
                        )
                        application.save(
                            update_fields=[
                                "status",
                                "reviewed_by",
                                "reviewed_at",
                                "admin_notes",
                            ]
                        )

                        messages.success(
                            request,
                            f"Application marked as needing additional information. "
                            f"Next steps: 1) Add notes below about what information is needed, "
                            f"2) Contact {application.first_name} {application.last_name} at "
                            f"{application.email} or {application.phone} to request the missing information.",
                        )

                        # TODO: Send request for more info email to applicant
                        logger.info(
                            f"Application {application.application_id} needs more info - marked by {request.user}"
                        )

                    elif review_action == "save_notes":
                        # Just save the notes without changing status
                        # (form.save(commit=False) already updated application.admin_notes)
                        application.save(update_fields=["admin_notes"])
                        messages.success(request, "Notes saved successfully.")
                        logger.info(
                            f"Application {application.application_id} notes updated by {request.user}"
                        )

                    return HttpResponseRedirect(request.path)

            except Exception as e:
                logger.error(f"Error processing application review: {e}")
                messages.error(
                    request,
                    f"There was an error processing your review: {str(e)}. "
                    f"Please check that all required information is complete and try again.",
                )
        else:
            # Provide specific error details when form validation fails
            action_name = dict(MembershipApplicationReviewForm.REVIEW_ACTIONS).get(
                review_action, "Unknown action"
            )
            error_messages = []

            if review_form.errors:
                for field, errors in review_form.errors.items():
                    for error in errors:
                        if field == "__all__":
                            error_messages.append(f"Form error: {error}")
                        else:
                            field_name = (
                                review_form.fields[field].label
                                or field.replace("_", " ").title()
                            )
                            error_messages.append(f"{field_name}: {error}")

            if error_messages:
                messages.error(
                    request,
                    f"Cannot {action_name.lower()}: {'; '.join(error_messages)}",
                )
            elif not review_action:
                messages.error(
                    request,
                    "Please select an action (Approve, Waitlist, etc.) and try again.",
                )
            else:
                messages.error(
                    request,
                    f"Cannot {action_name.lower()}: Please check all required fields and try again.",
                )
    else:
        review_form = MembershipApplicationReviewForm(instance=application)

    return render(
        request,
        "members/membership_application_detail.html",
        {
            "application": application,
            "review_form": review_form,
        },
    )


@active_member_required
def membership_waitlist(request):
    """
    Manage the membership waiting list - allows reordering of applications.
    Only accessible to membership managers.
    """

    # Check permissions
    if not (
        request.user.member_manager
        or request.user.webmaster
        or request.user.is_superuser
    ):
        raise PermissionDenied(
            "You do not have permission to manage the membership waiting list."
        )

    if request.method == "POST":
        # Handle waitlist reordering
        action = request.POST.get("action")
        application_id = request.POST.get("application_id")

        if action and application_id:
            try:
                application = get_object_or_404(
                    MembershipApplication,
                    application_id=application_id,
                    status="waitlisted",
                )

                if (
                    action == "move_up"
                    and application.waitlist_position
                    and application.waitlist_position > 1
                ):
                    # Swap with the application above
                    with transaction.atomic():
                        above_app = MembershipApplication.objects.filter(
                            status="waitlisted",
                            waitlist_position=application.waitlist_position - 1,
                        ).first()

                        if above_app:
                            # Swap positions
                            temp_pos = application.waitlist_position
                            application.waitlist_position = above_app.waitlist_position
                            above_app.waitlist_position = temp_pos

                            application.save(update_fields=["waitlist_position"])
                            above_app.save(update_fields=["waitlist_position"])

                            messages.success(
                                request,
                                f"Moved {application.full_name} up in the waiting list.",
                            )

                elif action == "move_down" and application.waitlist_position:
                    # Swap with the application below
                    with transaction.atomic():
                        below_app = MembershipApplication.objects.filter(
                            status="waitlisted",
                            waitlist_position=application.waitlist_position + 1,
                        ).first()

                        if below_app:
                            # Swap positions
                            temp_pos = application.waitlist_position
                            application.waitlist_position = below_app.waitlist_position
                            below_app.waitlist_position = temp_pos

                            application.save(update_fields=["waitlist_position"])
                            below_app.save(update_fields=["waitlist_position"])

                            messages.success(
                                request,
                                f"Moved {application.full_name} down in the waiting list.",
                            )

                elif action == "move_to_top" and application.waitlist_position:
                    # Move to position 1, shift everyone else down
                    if application.waitlist_position > 1:
                        with transaction.atomic():
                            old_position = application.waitlist_position
                            # Shift all applications above this one down by 1
                            MembershipApplication.objects.filter(
                                status="waitlisted",
                                waitlist_position__lt=old_position,
                            ).update(
                                waitlist_position=models.F("waitlist_position") + 1
                            )

                            # Move this application to position 1
                            application.waitlist_position = 1
                            application.save(update_fields=["waitlist_position"])

                            messages.success(
                                request,
                                f"Moved {application.full_name} to the top of the waiting list.",
                            )
                    else:
                        messages.info(
                            request,
                            f"{application.full_name} is already at the top of the waiting list.",
                        )

                elif action == "move_to_bottom" and application.waitlist_position:
                    # Move to the last position, shift everyone below up
                    old_position = application.waitlist_position
                    max_position = MembershipApplication.objects.filter(
                        status="waitlisted"
                    ).aggregate(max_pos=models.Max("waitlist_position"))["max_pos"]

                    if max_position and old_position < max_position:
                        with transaction.atomic():
                            # Shift all applications below this one up by 1
                            MembershipApplication.objects.filter(
                                status="waitlisted",
                                waitlist_position__gt=old_position,
                            ).update(
                                waitlist_position=models.F("waitlist_position") - 1
                            )

                            # Move this application to the last position
                            application.waitlist_position = max_position
                            application.save(update_fields=["waitlist_position"])

                            messages.success(
                                request,
                                f"Moved {application.full_name} to the bottom of the waiting list.",
                            )
                    else:
                        messages.info(
                            request,
                            f"{application.full_name} is already at the bottom of the waiting list.",
                        )

            except Exception as e:
                logger.error(f"Error reordering waitlist: {e}")
                messages.error(
                    request, "There was an error reordering the waiting list."
                )

        return HttpResponseRedirect(request.path)

    # Get all waitlisted applications in order
    waitlisted_applications = MembershipApplication.objects.filter(
        status="waitlisted"
    ).order_by("waitlist_position")

    return render(
        request,
        "members/membership_waitlist.html",
        {
            "applications": waitlisted_applications,
        },
    )


@require_http_methods(["GET", "POST"])
def membership_application_status(request, application_id):
    """
    Public status check for membership applications.
    Allows applicants to check their application status without logging in.
    Also allows withdrawal of pending applications via POST.
    """

    application = get_object_or_404(
        MembershipApplication, application_id=application_id
    )

    # Handle withdrawal request
    if request.method == "POST" and request.POST.get("action") == "withdraw":
        # Only allow withdrawal if application is still pending or under review
        if application.status in ["pending", "under_review", "additional_info_needed"]:
            application.status = "withdrawn"
            application.reviewed_at = timezone.now()
            application.save()

            logger.info(
                f"Application withdrawn by applicant: {application.email} "
                f"({application.first_name} {application.last_name}) - ID: {application.application_id}"
            )

            # Notify membership managers about the withdrawal
            from .signals import notify_membership_managers_of_withdrawal

            notify_membership_managers_of_withdrawal(application)

            messages.success(
                request,
                "Your application has been withdrawn successfully. "
                "Thank you for your interest in our club.",
            )
        else:
            messages.error(
                request, "This application cannot be withdrawn at this time."
            )

        # Redirect back to status page to prevent re-submission
        return HttpResponseRedirect(request.path)

    # Basic security - only show limited information
    context = {
        "application": application,
        "status_display": application.get_status_display(),
        "submitted_date": application.submitted_at,
        "applicant_name": application.first_name,  # Only show first name for privacy
        "can_withdraw": application.status
        in ["pending", "under_review", "additional_info_needed"],
    }

    return render(request, "members/membership_application_status.html", context)
