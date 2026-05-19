import re
from collections import defaultdict

from django.core.exceptions import ValidationError
from import_export import resources

from .models import Member
from .utils.username import generate_username


class MemberResource(resources.ModelResource):
    """Normalize imported member fields before persistence."""

    _SSA_NULL_TOKENS = {"", "0", "null", "none", "na", "n/a", "unknown"}
    _LEGACY_USERNAME_NULL_TOKENS = {"", "null", "none", "na", "n/a", "unknown"}

    class Meta:
        model = Member

    def before_import(self, dataset, **kwargs):
        """Preload usernames once to avoid per-row existence queries during import."""
        self._batch_usernames = defaultdict(set)
        self._existing_usernames = defaultdict(set)
        for pk, username in (
            Member.objects.exclude(username__isnull=True)
            .exclude(username="")
            .values_list("pk", "username")
        ):
            self._existing_usernames[self._username_key(username)].add(pk)

    @staticmethod
    def _username_key(username):
        return username.casefold()

    def _normalize_username(self, raw_value):
        if raw_value is None:
            return ""

        username = str(raw_value).strip().lower()
        max_length = Member._meta.get_field("username").max_length
        username = username[:max_length]
        if not username:
            return ""

        # Keep imported usernames in the same lower-case ASCII family used by
        # generated usernames and reject malformed values.
        if not re.fullmatch(r"[a-z0-9._@+-]+", username):
            return ""

        try:
            Member._meta.get_field("username").run_validators(username)
        except ValidationError:
            return ""

        return username

    def _username_is_taken(self, username, current_pk=None):
        username_key = self._username_key(username)
        existing_with_key = self._existing_usernames.get(username_key, set())

        if current_pk is not None:
            existing_with_key = existing_with_key - {current_pk}

        batch_reserved_by_pks = self._batch_usernames.get(username_key, set())
        if current_pk is not None:
            batch_reserved_by_pks = batch_reserved_by_pks - {current_pk, None}
        else:
            batch_reserved_by_pks = batch_reserved_by_pks - {None}

        return bool(existing_with_key) or bool(batch_reserved_by_pks)

    @staticmethod
    def _append_suffix(base_username, counter):
        max_length = Member._meta.get_field("username").max_length
        suffix = str(counter)
        truncated_base = base_username[: max_length - len(suffix)]
        return f"{truncated_base}{suffix}"

    def _reserve_unique_username(self, instance, requested_username):
        candidate = self._normalize_username(requested_username)
        current_pk = instance.pk

        if candidate and not self._username_is_taken(candidate, current_pk=current_pk):
            self._batch_usernames[self._username_key(candidate)].add(current_pk or None)
            return candidate

        # Reuse the canonical first.last generator used by account creation.
        base_candidate = generate_username(
            instance.first_name or "",
            instance.last_name or "",
        )

        if not self._username_is_taken(base_candidate, current_pk=current_pk):
            self._batch_usernames[self._username_key(base_candidate)].add(
                current_pk or None
            )
            return base_candidate

        counter = 1
        username = self._append_suffix(base_candidate, counter)
        while self._username_is_taken(username, current_pk=current_pk):
            counter += 1
            username = self._append_suffix(base_candidate, counter)

        self._batch_usernames[self._username_key(username)].add(current_pk or None)
        return username

    @staticmethod
    def _normalize_nullable_value(raw_value, null_tokens):
        if raw_value is None:
            return None

        normalized = str(raw_value).strip()
        if normalized.lower() in null_tokens:
            return None
        return normalized

    def before_import_row(self, row, **kwargs):
        """Treat placeholder SSA values as missing so unique constraint is not hit."""
        row["SSA_member_number"] = self._normalize_nullable_value(
            row.get("SSA_member_number"),
            self._SSA_NULL_TOKENS,
        )
        row["legacy_username"] = self._normalize_nullable_value(
            row.get("legacy_username"),
            self._LEGACY_USERNAME_NULL_TOKENS,
        )
        row["username"] = self._normalize_username(row.get("username"))

    def before_save_instance(self, instance, row, **kwargs):
        """Enforce NULL (not empty string) for missing values on final save path."""
        instance.username = self._reserve_unique_username(instance, instance.username)
        instance.SSA_member_number = self._normalize_nullable_value(
            instance.SSA_member_number,
            self._SSA_NULL_TOKENS,
        )
        instance.legacy_username = self._normalize_nullable_value(
            instance.legacy_username,
            self._LEGACY_USERNAME_NULL_TOKENS,
        )
