from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils.timezone import now

from duty_roster.models import DutyAssignment
from logsheet.models import Flight
from members.models import Member
from notifications.models import Notification
from utils.email import send_mail
from utils.management.commands.base_cronjob import BaseCronJobCommand


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
        recent_flight_cutoff = today - timedelta(days=lookback_months * 30)

        # Get members who have flown as pilot in the lookback period
        active_flyers = (
            eligible_members.filter(
                flights_as_pilot__logsheet__log_date__gte=recent_flight_cutoff,
                flights_as_pilot__logsheet__finalized=True,
            )
            .annotate(flight_count=Count("flights_as_pilot", distinct=True))
            .filter(flight_count__gte=min_flights)
            .distinct()
        )

        self.log_info(
            f"Found {active_flyers.count()} actively flying members ({min_flights}+ flights)"
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
        """Check if member has performed any duty since cutoff_date"""

        # Check DutyAssignment assignments
        duty_assignments = DutyAssignment.objects.filter(
            Q(duty_officer=member)
            | Q(assistant_duty_officer=member)
            | Q(instructor=member)
            | Q(surge_instructor=member)
            | Q(tow_pilot=member)
            | Q(surge_tow_pilot=member),
            date__gte=cutoff_date,
        ).exists()

        return duty_assignments

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

        report_lines = [
            f"Monthly Duty Delinquency Report - {today.strftime('%B %Y')}",
            "",
            f"The following {len(duty_delinquents)} member(s) have been actively flying but have not performed any duty in the last {lookback_months} months:",
            "",
        ]

        # Sort by flight count (most active first)
        duty_delinquents.sort(key=lambda x: x["flight_count"], reverse=True)

        for i, delinquent in enumerate(duty_delinquents, 1):
            member = delinquent["member"]
            report_lines.extend(
                [
                    f"{i}. {member.full_display_name}",
                    f"   • Email: {member.email or 'No email on file'}",
                    f"   • Membership Status: {member.membership_status}",
                    f"   • Member for: {delinquent['membership_duration']}",
                    f"   • Flights in period: {delinquent['flight_count']}",
                    f"   • Most recent flight: {delinquent['most_recent_flight']}",
                    "",
                ]
            )

        report_lines.extend(
            [
                "Please follow up with these members regarding their duty obligations.",
                "",
                "📊 DETAILED REPORT WITH MEMBER PHOTOS AND CONTACT INFO:",
                f"   {settings.SITE_URL}/duty_roster/duty-delinquents/detail/",
                "",
                "Criteria for this report:",
                f"• Members with 3+ months of membership",
                f"• Members who have flown 3+ times in the last {lookback_months} months",
                f"• Members who have NOT performed any duty in the last {lookback_months} months",
                "",
                "Additional Resources:",
                f"• Member Directory: {settings.SITE_URL}/members/",
                f"• Duty Roster: {settings.SITE_URL}/duty_roster/",
                "",
                "- Manage2Soar Automated Reports",
            ]
        )

        message = "\n".join(report_lines)

        try:
            # Send email report
            send_mail(
                subject=subject,
                message=message,
                from_email="noreply@default.manage2soar.com",
                recipient_list=recipient_list,
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
