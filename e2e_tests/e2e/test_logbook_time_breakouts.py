"""Focused E2E tests for logbook time breakout behavior (Issue #762)."""

from datetime import date, time, timedelta

from django.urls import reverse

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Flight, Glider, Logsheet


class TestLogbookTimeBreakouts(DjangoPlaywrightTestCase):
    def _normalize_header_text(self, text):
        return " ".join(text.split())

    def _header_index_map(self, table):
        headers = [
            table.locator("thead tr").last.locator("th").nth(i).inner_text().strip()
            for i in range(table.locator("thead tr").last.locator("th").count())
        ]
        return {name: idx for idx, name in enumerate(headers)}

    def _summary_header_index_map(self, table):
        first_row = table.locator("thead tr").nth(0).locator("th")
        second_row = table.locator("thead tr").nth(1).locator("th")

        index_map = {}
        current_column = 0
        second_row_index = 0

        for idx in range(first_row.count()):
            cell = first_row.nth(idx)
            group_label = self._normalize_header_text(cell.inner_text())
            colspan = int(cell.get_attribute("colspan") or "1")
            rowspan = int(cell.get_attribute("rowspan") or "1")

            if rowspan >= 2:
                index_map[group_label] = current_column
                current_column += colspan
                continue

            for _ in range(colspan):
                sub_label = self._normalize_header_text(
                    second_row.nth(second_row_index).inner_text()
                )
                index_map[f"{group_label} {sub_label}"] = current_column
                current_column += 1
                second_row_index += 1

        return index_map

    def _create_common_members(self, pilot_username):
        pilot = self.create_test_member(
            username=pilot_username,
            glider_rating="rated",
        )
        pilot.private_glider_checkride_date = date(2020, 1, 1)
        pilot.save(update_fields=["private_glider_checkride_date"])

        instructor = self.create_test_member(
            username=f"{pilot_username}_instructor",
            instructor=True,
            glider_rating="rated",
        )
        return pilot, instructor

    def test_rated_pilot_dual_row_shows_dual_and_pic(self):
        """Rated pilot with instructor logs both Dual Received and PIC on logbook row."""
        pilot, instructor = self._create_common_members("e2e_logbook_rated")

        airfield = Airfield.objects.create(name="Front Royal", identifier="KFRR")
        glider = Glider.objects.create(
            n_number="N762E2E1",
            make="Schleicher",
            model="ASK-21",
            club_owned=True,
            is_active=True,
        )
        logsheet = Logsheet.objects.create(
            log_date=date(2024, 6, 1),
            airfield=airfield,
            created_by=pilot,
        )
        Flight.objects.create(
            logsheet=logsheet,
            pilot=pilot,
            instructor=instructor,
            glider=glider,
            launch_method="tow",
            launch_time=time(10, 0),
            landing_time=time(10, 25),
        )

        self.login(username=pilot.username)
        self.page.goto(
            f"{self.live_server_url}{reverse('instructors:member_logbook')}?show_all_years=1"
        )
        self.page.wait_for_selector("text=Logbook for")

        logbook_table = self.page.locator(
            "table.table", has=self.page.locator("thead th:text-is('Date')")
        ).first
        col = self._header_index_map(logbook_table)

        row = logbook_table.locator("tbody tr", has_text="2024-06-01").first
        dual = row.locator("td").nth(col["Dual"]).inner_text().strip()
        pic = row.locator("td").nth(col["PIC"]).inner_text().strip()
        total = row.locator("td").nth(col["Total"]).inner_text().strip()

        assert dual == "0:25"
        assert pic == "0:25"
        assert total == "0:25"

    def test_default_view_hides_old_rows_but_summary_is_all_time(self):
        """Default logbook view still shows all-time totals in the glider summary table."""
        pilot, instructor = self._create_common_members("e2e_logbook_alltime")

        airfield = Airfield.objects.create(name="Summit Point", identifier="KSUM")
        glider = Glider.objects.create(
            n_number="N762E2E2",
            make="Schleicher",
            model="ASK-21",
            club_owned=True,
            is_active=True,
        )

        old_date = date.today() - timedelta(days=365 * 5)
        recent_date = date.today() - timedelta(days=7)

        old_logsheet = Logsheet.objects.create(
            log_date=old_date,
            airfield=airfield,
            created_by=pilot,
        )
        Flight.objects.create(
            logsheet=old_logsheet,
            pilot=pilot,
            instructor=instructor,
            glider=glider,
            launch_method="tow",
            launch_time=time(9, 0),
            landing_time=time(9, 30),
        )

        recent_logsheet = Logsheet.objects.create(
            log_date=recent_date,
            airfield=airfield,
            created_by=pilot,
        )
        Flight.objects.create(
            logsheet=recent_logsheet,
            pilot=pilot,
            instructor=instructor,
            glider=glider,
            launch_method="tow",
            launch_time=time(10, 0),
            landing_time=time(10, 45),
        )

        self.login(username=pilot.username)
        self.page.goto(f"{self.live_server_url}{reverse('instructors:member_logbook')}")
        self.page.wait_for_selector("text=Logbook for")

        assert self.page.locator(f"text={old_date.isoformat()}").count() == 0
        assert self.page.locator(f"text={recent_date.isoformat()}").count() > 0

        self.page.wait_for_selector("text=All-Time Glider Time Summary")
        summary_table = self.page.locator(
            "h3:has-text('All-Time Glider Time Summary') + p + div table"
        ).first
        summary_row = summary_table.locator(
            "tbody tr", has_text="Schleicher ASK-21"
        ).first

        col = self._summary_header_index_map(summary_table)

        dual_count = (
            summary_row.locator("td").nth(col["Dual Received #"]).inner_text().strip()
        )
        dual = (
            summary_row.locator("td")
            .nth(col["Dual Received Time"])
            .inner_text()
            .strip()
        )
        instruction_count = (
            summary_row.locator("td")
            .nth(col["Instruction Given #"])
            .inner_text()
            .strip()
        )
        instruction_time = (
            summary_row.locator("td")
            .nth(col["Instruction Given Time"])
            .inner_text()
            .strip()
        )
        pic_summary_count = (
            summary_row.locator("td").nth(col["PIC Summary #"]).inner_text().strip()
        )
        pic_summary = (
            summary_row.locator("td").nth(col["PIC Summary Time"]).inner_text().strip()
        )
        total_count = (
            summary_row.locator("td").nth(col["Total Time #"]).inner_text().strip()
        )
        total = (
            summary_row.locator("td").nth(col["Total Time Time"]).inner_text().strip()
        )

        assert dual_count == "2"
        assert dual == "1:15"
        assert instruction_count == "0"
        assert instruction_time == "0:00"
        assert pic_summary_count == "2"
        assert pic_summary == "1:15"
        assert total_count == "2"
        assert total == "1:15"
