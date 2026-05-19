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
        """Track usernames assigned in this import run to avoid same-batch collisions."""
        self._batch_usernames = set()

    @staticmethod
    def _normalize_username(raw_value):
        if raw_value is None:
            return ""
        return str(raw_value).strip()

    def _username_is_taken(self, username, current_pk=None):
        query = Member.objects.filter(username=username)
        if current_pk is not None:
            query = query.exclude(pk=current_pk)
        return query.exists() or username in self._batch_usernames

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
            self._batch_usernames.add(candidate)
            return candidate

        # Reuse the canonical first.last generator used by account creation.
        base_candidate = generate_username(
            instance.first_name or "",
            instance.last_name or "",
        )

        if not self._username_is_taken(base_candidate, current_pk=current_pk):
            self._batch_usernames.add(base_candidate)
            return base_candidate

        counter = 1
        username = self._append_suffix(base_candidate, counter)
        while self._username_is_taken(username, current_pk=current_pk):
            counter += 1
            username = self._append_suffix(base_candidate, counter)

        self._batch_usernames.add(username)
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
