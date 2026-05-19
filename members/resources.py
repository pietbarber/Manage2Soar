import re
from collections import defaultdict

from django.core.exceptions import ValidationError
from import_export import resources

from .models import Member

# Shared safe member CSV schema used by both import-export resource and
# custom admin CSV action to avoid schema drift across export paths.
MEMBER_CSV_FIELDS = (
    "id",
    "username",
    "first_name",
    "middle_initial",
    "last_name",
    "name_suffix",
    "nickname",
    "email",
    "phone",
    "mobile_phone",
    "emergency_contact",
    "membership_status",
    "date_joined",
    "private_glider_checkride_date",
    "instructor",
    "towpilot",
    "duty_officer",
    "assistant_duty_officer",
    "director",
    "member_manager",
    "rostermeister",
    "webmaster",
    "secretary",
    "treasurer",
    "safety_officer",
    "address",
    "city",
    "state_code",
    "state_freeform",
    "zip_code",
    "country",
    "pilot_certificate_number",
    "SSA_member_number",
    "legacy_username",
    "ssa_url",
    "glider_rating",
    "public_notes",
    "private_notes",
)


class MemberResource(resources.ModelResource):
    """Normalize imported member fields before persistence."""

    _SSA_NULL_TOKENS = {"", "0", "null", "none", "na", "n/a", "unknown"}
    _LEGACY_USERNAME_NULL_TOKENS = {"", "0", "null", "none", "na", "n/a", "unknown"}

    class Meta:
        model = Member
        fields = MEMBER_CSV_FIELDS

    def before_import(self, dataset, **kwargs):
        """Preload usernames once to avoid per-row existence queries during import."""
        self._batch_usernames = defaultdict(set)
        self._token_reservations: dict = (
            {}
        )  # row_token -> currently reserved username_key
        self._existing_usernames = defaultdict(set)
        self._pk_current_username_key: dict = {}
        self._pk_current_username: dict = {}
        for pk, username in (
            Member.objects.exclude(username__isnull=True)
            .exclude(username="")
            .values_list("pk", "username")
        ):
            username_key = self._username_key(username)
            self._existing_usernames[username_key].add(pk)
            self._pk_current_username_key[pk] = username_key
            self._pk_current_username[pk] = username

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

    @staticmethod
    def _make_base_username(first_name: str, last_name: str) -> str:
        """Build the canonical first.last base username without any DB lookups."""
        first_clean = re.sub(r"[^A-Za-z]", "", first_name).lower()
        last_clean = re.sub(r"[^A-Za-z]", "", last_name).lower()

        if not first_clean and not last_clean:
            base = "user"
        elif not first_clean:
            base = last_clean
        elif not last_clean:
            base = first_clean
        else:
            base = f"{first_clean}.{last_clean}"

        max_length = Member._meta.get_field("username").max_length
        return base[:max_length]

    def _reserve_in_batch(self, row_token, username, current_pk=None):
        """Reserve a username for a row token, releasing any prior reservation."""
        new_key = self._username_key(username)
        prev_key = self._token_reservations.get(row_token)
        if prev_key is not None and prev_key != new_key:
            self._batch_usernames[prev_key].discard(row_token)
        self._batch_usernames[new_key].add(row_token)
        self._token_reservations[row_token] = new_key

        # Keep the preloaded existing-username index aligned with in-batch
        # renames for existing members so freed names can be reclaimed later
        # in the same import run.
        if current_pk is not None:
            prev_existing_key = self._pk_current_username_key.get(current_pk)
            if prev_existing_key is not None and prev_existing_key != new_key:
                self._existing_usernames[prev_existing_key].discard(current_pk)
            self._existing_usernames[new_key].add(current_pk)
            self._pk_current_username_key[current_pk] = new_key
            self._pk_current_username[current_pk] = username

    def _preserve_existing_username_if_missing(self, instance):
        """Keep username stable for updates when incoming value normalizes to empty."""
        if instance.pk is None:
            return False

        candidate = self._normalize_username(instance.username)
        if candidate:
            return False

        preserved_username = self._pk_current_username.get(instance.pk)
        if not preserved_username:
            return False

        self._reserve_in_batch(instance.pk, preserved_username, current_pk=instance.pk)
        instance.username = preserved_username
        return True

    def _username_is_taken(self, username, current_pk=None, row_token=None):
        username_key = self._username_key(username)
        existing_with_key = self._existing_usernames.get(username_key, set())

        if current_pk is not None:
            existing_with_key = existing_with_key - {current_pk}

        batch_reserved_by = self._batch_usernames.get(username_key, set())
        if row_token is not None:
            batch_reserved_by = batch_reserved_by - {row_token}

        return bool(existing_with_key) or bool(batch_reserved_by)

    @staticmethod
    def _append_suffix(base_username, counter):
        max_length = Member._meta.get_field("username").max_length
        suffix = str(counter)
        truncated_base = base_username[: max_length - len(suffix)]
        return f"{truncated_base}{suffix}"

    def _reserve_unique_username(self, instance, requested_username):
        candidate = self._normalize_username(requested_username)
        current_pk = instance.pk
        # Use pk for existing instances, id(instance) for new ones — each new
        # instance object has a unique id() so same-file new-row collisions
        # are correctly detected rather than blindly excluded.
        row_token = current_pk if current_pk is not None else id(instance)

        if candidate and not self._username_is_taken(
            candidate, current_pk=current_pk, row_token=row_token
        ):
            self._reserve_in_batch(row_token, candidate, current_pk=current_pk)
            return candidate

        # Build the canonical first.last base without DB queries; uniqueness
        # is enforced entirely by the in-memory preloaded set + batch tracking.
        base_candidate = self._make_base_username(
            instance.first_name or "",
            instance.last_name or "",
        )

        if not self._username_is_taken(
            base_candidate, current_pk=current_pk, row_token=row_token
        ):
            self._reserve_in_batch(row_token, base_candidate, current_pk=current_pk)
            return base_candidate

        counter = 1
        username = self._append_suffix(base_candidate, counter)
        while self._username_is_taken(
            username, current_pk=current_pk, row_token=row_token
        ):
            counter += 1
            username = self._append_suffix(base_candidate, counter)

        self._reserve_in_batch(row_token, username, current_pk=current_pk)
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
        if not self._preserve_existing_username_if_missing(instance):
            instance.username = self._reserve_unique_username(
                instance, instance.username
            )

        # Imported users bypass create_user(); ensure new accounts cannot auth
        # until credentials are explicitly configured.
        if instance._state.adding and not instance.password:
            instance.set_unusable_password()

        instance.SSA_member_number = self._normalize_nullable_value(
            instance.SSA_member_number,
            self._SSA_NULL_TOKENS,
        )
        instance.legacy_username = self._normalize_nullable_value(
            instance.legacy_username,
            self._LEGACY_USERNAME_NULL_TOKENS,
        )
