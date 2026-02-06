from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.template.loader import render_to_string
from django.utils.timezone import now

from duty_roster.utils.delinquents import apply_duty_delinquent_exemptions
from logsheet.models import Flight, Logsheet
from members.models import Member
from notifications.models import Notification
from siteconfig.models import SiteConfiguration
from utils.email import send_mail
from utils.email_helpers import get_absolute_club_logo_url
from utils.management.commands.base_cronjob import BaseCronJobCommand
from utils.url_helpers import build_absolute_url, get_canonical_url


class Command(BaseCronJobCommand):
    help = "Generate monthly report of members who are actively flying but haven't performed duty in 12 months"
    job_name = "report_duty_delinquents"
    max_execution_time = timedelta(minutes=30)  # Complex analysis may take time

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument(
            "--lookback-months",
            type=int,
            default=12,
            help="How many months to look back for duty participation (default: 12)",
        )
        parser.add_argument(
            "--min-flights",
            type=int,
            default=3,
            help='Minimum number of flights in the period to be considered "actively flying" (default: 3)',
        )
        parser.add_argument(
            "--min-membership-months",
            type=int,
            default=3,
            help="Minimum months of membership before duty obligation begins (default: 3)",
        )

    def execute_job(self, *args, **options):
        lookback_months = options.get("lookback_months", 12)
        min_flights = options.get("min_flights", 3)
        min_membership_months = options.get("min_membership_months", 3)

        # Calculate date ranges
        today = now().date()
        duty_cutoff_date = today - timedelta(days=lookback_months * 30)  # Approximate
        membership_cutoff_date = today - timedelta(days=min_membership_months * 30)

        self.log_info(f"Analyzing duty participation since {duty_cutoff_date}")
        self.log_info(f"Looking for members joined before {membership_cutoff_date}")

        # Step 1: Find all members who have been in the club for 3+ months
        # Use centralized helper for active status filtering
        from members.utils.membership import get_active_membership_statuses

        active_status_names = get_active_membership_statuses()

        eligible_members = Member.objects.filter(
            Q(joined_club__lt=membership_cutoff_date)
            | Q(joined_club__isnull=True),  # Include null join dates
            membership_status__in=active_status_names,  # Only active statuses
        )

        self.log_info(
            f"Found {eligible_members.count()} eligible members (3+ months membership)"
        )

        # Step 2: Find members who have been actively flying
        # Apply duty delinquency exemptions (treasurer, emeritus)
        recent_flight_cutoff = today - timedelta(days=lookback_months * 30)

        # Get members who have flown as pilot in the lookback period
        active_flyers = apply_duty_delinquent_exemptions(
            eligible_members.filter(
                flights_as_pilot__logsheet__log_date__gte=recent_flight_cutoff,
                flights_as_pilot__logsheet__finalized=True,
            )
            .annotate(flight_count=Count("flights_as_pilot", distinct=True))
            .filter(flight_count__gte=min_flights)
            .distinct()
        )

        self.log_info(
            f"Found {active_flyers.count()} actively flying members ({min_flights}+ flights, excluding treasurer and emeritus)"
        )

        if not active_flyers.exists():
            self.log_info(
                "No actively flying members found to check for duty delinquency"
            )
            return

        # Step 3: Check duty participation for active flyers
        duty_delinquents = []

        for member in active_flyers:
            # Check if member has performed any duty in the lookback period
            duty_performed = self._has_performed_duty(member, duty_cutoff_date)

            if not duty_performed:
                # Get member's flight details for the report
                flight_count = Flight.objects.filter(
                    pilot=member,
                    logsheet__log_date__gte=recent_flight_cutoff,
                    logsheet__finalized=True,
                ).count()

                # Get most recent flight date
                recent_flight = (
                    Flight.objects.filter(
                        pilot=member,
                        logsheet__log_date__gte=recent_flight_cutoff,
                        logsheet__finalized=True,
                    )
                    .order_by("-logsheet__log_date")
                    .first()
                )

                duty_delinquents.append(
                    {
                        "member": member,
                        "flight_count": flight_count,
                        "most_recent_flight": (
                            recent_flight.logsheet.log_date if recent_flight else None
                        ),
                        "membership_duration": self._calculate_membership_duration(
                            member, today
                        ),
                    }
                )

        if not duty_delinquents:
            self.log_success(
                "No duty delinquent members found - everyone is participating!"
            )
            return

        self.log_warning(f"Found {len(duty_delinquents)} duty delinquent member(s)")

        # Step 4: Generate and send report
        if not options.get("dry_run"):
            self._send_delinquency_report(duty_delinquents, lookback_months)
            self.log_success("Duty delinquency report sent to Member Meister")
        else:
            # Check member managers for dry-run logging
            from members.utils.membership import get_active_membership_statuses

            active_status_names = get_active_membership_statuses()

            member_meisters = Member.objects.filter(
                member_manager=True,
                membership_status__in=active_status_names,
                email__isnull=False,
            ).exclude(email="")

            if member_meisters.exists():
                self.log_info(
                    f"Would send report to {member_meisters.count()} Member Manager(s): {', '.join([mm.full_display_name for mm in member_meisters])}"
                )
            else:
                self.log_warning(
                    "No Member Managers found, would use fallback email: president@skylinesoaring.org"
                )

            self.log_info("Would send duty delinquency report to Member Meister")
            for delinquent in duty_delinquents:
                member = delinquent["member"]
                self.log_info(
                    f"  - {member.full_display_name}: {delinquent['flight_count']} flights, "
                    f"last flight {delinquent['most_recent_flight']}, "
                    f"member for {delinquent['membership_duration']}"
                )

    def _has_performed_duty(self, member, cutoff_date):
        """
        Check if member has performed any duty since cutoff_date.

        Only checks ACTUAL duty performed (flight activity and logsheet assignments),
        not scheduled duty (DutyAssignment). Being scheduled but not showing up
        doesn't count as performing duty.

        Checks Flight records first (instructor/tow pilot activity), then Logsheet
        duty assignments. This order matches the web view implementation.
        """

        # Check Flight records for instructors and tow pilots first
        # (actual flight activity is the most direct form of duty)
        flight_duty = Flight.objects.filter(
            Q(instructor=member) | Q(tow_pilot=member),
            logsheet__log_date__gte=cutoff_date,
            logsheet__finalized=True,
        ).exists()

        if flight_duty:
            return True

        # Also check Logsheet duty assignments (actual operations)
        # (they may have served duty but not flown)
        logsheet_duty = Logsheet.objects.filter(
            Q(duty_officer=member)
            | Q(assistant_duty_officer=member)
            | Q(duty_instructor=member)
            | Q(surge_instructor=member)
            | Q(tow_pilot=member)
            | Q(surge_tow_pilot=member),
            log_date__gte=cutoff_date,
            finalized=True,
        ).exists()

        return logsheet_duty

    def _calculate_membership_duration(self, member, today):
        """Calculate how long the member has been in the club"""
        if member.joined_club:
            delta = today - member.joined_club
            years = delta.days // 365
            months = (delta.days % 365) // 30

            if years > 0:
                return f"{years} year(s), {months} month(s)"
            else:
                return f"{months} month(s)"
        else:
            return "Unknown (no join date)"

    def _send_delinquency_report(self, duty_delinquents, lookback_months):
        """Send the duty delinquency report to appropriate personnel"""

        # Find Member Managers (use the proper member_manager boolean field)
        # Use centralized helper for active membership status filtering
        from members.utils.membership import get_active_membership_statuses

        active_status_names = get_active_membership_statuses()

        member_meisters = Member.objects.filter(
            member_manager=True,
            membership_status__in=active_status_names,
            email__isnull=False,
        ).exclude(email="")

        # Fallback to a configured email if no member meisters found
        if not member_meisters.exists():
            recipient_list = ["president@skylinesoaring.org"]  # Fallback
            self.log_warning("No Member Managers found, using fallback email")
        else:
            recipient_list = [mm.email for mm in member_meisters]
            self.log_info(
                f"Found {member_meisters.count()} Member Manager(s): {', '.join([mm.full_display_name for mm in member_meisters])}"
            )

        # Build report content
        today = now().date()
        subject = f"Monthly Duty Delinquency Report - {len(duty_delinquents)} Member(s)"

        # Prepare template context
        config = SiteConfiguration.objects.first()
        site_url = get_canonical_url()

        # Build URLs
        detail_report_url = build_absolute_url("/duty_roster/duty-delinquents/detail/")
        member_directory_url = build_absolute_url("/members/")
        duty_roster_url = build_absolute_url("/duty_roster/")

        # Sort by flight count (most active first)
        duty_delinquents.sort(key=lambda x: x["flight_count"], reverse=True)

        # Format delinquent data for templates
        formatted_delinquents = [
            {
                "name": delinquent["member"].full_display_name,
                "email": delinquent["member"].email or "No email on file",
                "membership_status": delinquent["member"].membership_status,
                "membership_duration": delinquent["membership_duration"],
                "flight_count": delinquent["flight_count"],
                "most_recent_flight": delinquent["most_recent_flight"],
            }
            for delinquent in duty_delinquents
        ]

        context = {
            "report_date": today.strftime("%B %Y"),
            "delinquent_count": len(duty_delinquents),
            "lookback_months": lookback_months,
            "delinquents": formatted_delinquents,
            "club_name": config.club_name if config else "Soaring Club",
            "club_logo_url": get_absolute_club_logo_url(config),
            "detail_report_url": detail_report_url,
            "member_directory_url": member_directory_url,
            "duty_roster_url": duty_roster_url,
        }

        # Render email templates
        html_message = render_to_string(
            "duty_roster/emails/duty_delinquency_report.html", context
        )
        text_message = render_to_string(
            "duty_roster/emails/duty_delinquency_report.txt", context
        )

        # Build from email
        default_from = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
        if "@" in default_from:
            domain = default_from.split("@")[-1]
            from_email = f"noreply@{domain}"
        elif config and config.domain_name:
            from_email = f"noreply@{config.domain_name}"
        else:
            from_email = "noreply@manage2soar.com"

        try:
            # Send email report
            send_mail(
                subject=subject,
                message=text_message,
                from_email=from_email,
                recipient_list=recipient_list,
                html_message=html_message,
                fail_silently=False,
            )

            # Create in-app notifications for member meisters
            for member_meister in member_meisters:
                Notification.objects.create(
                    user=member_meister,
                    message=f"📊 Monthly duty delinquency report: {len(duty_delinquents)} member(s) need follow-up",
                    url="/duty_roster/duty-delinquents/detail/",
                )

            self.log_success(
                f"Sent duty delinquency report to: {', '.join(recipient_list)}"
            )

        except Exception as e:
            self.log_error(f"Failed to send duty delinquency report: {str(e)}")
