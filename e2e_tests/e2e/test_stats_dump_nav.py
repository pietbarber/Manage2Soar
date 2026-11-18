from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase


class TestStatsDumpNav(DjangoPlaywrightTestCase):
    def test_stats_dump_link_visible_for_stats_monger(self):
        member = self.create_test_member(
            username="stats_monger_user", stats_monger=True
        )
        member.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get(
                    app_label="logsheet", model="logsheet"
                ),
                codename="can_export_stats_dump",
            )
        )
        self.login(username=member.username)

        self.page.goto(f"{self.live_server_url}{reverse('home')}")
        self.page.click("#logsheetDropdown")
        self.page.wait_for_selector("#logsheetDropdown + .dropdown-menu.show")

        href = reverse("logsheet:stats_dump_export_queue")
        link = self.page.locator(f'a.dropdown-item[href="{href}"]')
        assert link.count() == 1

    def test_stats_dump_link_hidden_for_non_stats_monger(self):
        member = self.create_test_member(username="non_stats_user", stats_monger=False)
        self.login(username=member.username)

        self.page.goto(f"{self.live_server_url}{reverse('home')}")
        self.page.click("#logsheetDropdown")
        self.page.wait_for_selector("#logsheetDropdown + .dropdown-menu.show")

        href = reverse("logsheet:stats_dump_export_queue")
        link = self.page.locator(f'a.dropdown-item[href="{href}"]')
        assert link.count() == 0
