"""Browser coverage for offline reference-data caching on the manage page.

Regression guard for the missing-comma syntax error that previously broke
``cacheReferenceData()`` (logsheet_manage.html) — the browser rejected the
whole inline script, so ``navigator.onLine`` auto-caching on page load never
ran and the IndexedDB ``members`` store stayed empty, leaving offline flight
entry unavailable.

This test loads the manage page, waits for the online auto-cache to populate
the ``members`` store, and asserts a member with a blank last name is cached
with ``lastName === ""`` (the actual surname, not a fallback).
"""

import time
from datetime import date

from django.urls import reverse

from e2e_tests.e2e.conftest import DjangoPlaywrightTestCase
from logsheet.models import Airfield, Logsheet
from siteconfig.models import SiteConfiguration


class TestOfflineReferenceDataCache(DjangoPlaywrightTestCase):
    """Verify the manage page's reference-data cache runs in the browser."""

    def setUp(self):
        super().setUp()
        self.admin = self.create_test_member(username="cacheadmin", is_superuser=True)
        # A blank-last-name member exercises the "cache the actual surname"
        # path in cacheReferenceData (no fallback to the last word of `name`).
        self.blank_surname = self.create_test_member(
            username="blanksurname",
            first_name="Zulu",
            last_name="",
        )
        SiteConfiguration.objects.create(
            club_name="Cache Club",
            domain_name="cache.example.com",
            club_abbreviation="CCH",
        )
        self.airfield = Airfield.objects.create(
            identifier="KWEB",
            name="Cache Airfield",
            is_active=True,
        )
        self.logsheet = Logsheet.objects.create(
            log_date=date.today(),
            airfield=self.airfield,
            created_by=self.admin,
        )
        self.login(username="cacheadmin")

    def test_page_load_caches_members_with_actual_blank_last_name(self):
        self.page.goto(
            f"{self.live_server_url}{reverse('logsheet:manage', kwargs={'pk': self.logsheet.pk})}"
        )
        # The page auto-caches reference data ~2s after load while online.
        # cacheReferenceData() does `clear('members')` then puts members
        # one-by-one, so poll the SAME member by id until it is stably present
        # (a bare count > 0 would return mid-clear or before this member lands).
        # A populated members store also proves the inline script executed —
        # the missing-comma regression left it empty because the IIFE crashed.
        target_id = int(self.blank_surname.pk)
        reader = """
            (targetId) => new Promise((resolve) => {
              if (typeof indexedDB === 'undefined') { resolve(null); return; }
              const req = indexedDB.open('manage2soar-offline');
              req.onerror = () => resolve(null);
              req.onsuccess = () => {
                let store;
                try {
                  store = req.result.transaction('members', 'readonly').objectStore('members');
                } catch (e) { resolve(null); return; }
                const r = store.get(targetId);
                r.onsuccess = () => resolve(r.result == null ? null : r.result);
                r.onerror = () => resolve(null);
              };
            })
        """
        entry = None
        start = time.monotonic()
        while time.monotonic() - start < 25:
            entry = self.page.evaluate(reader, target_id)
            if entry is not None:
                break
            self.page.wait_for_timeout(300)

        # The member must be present in the cache with its real (empty)
        # last name — a fallback would have produced a non-empty surname.
        self.assertIsNotNone(
            entry, "blank-surname member missing from cached reference data"
        )
        self.assertEqual(entry["lastName"], "")
