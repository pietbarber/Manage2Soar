from django.conf import settings

from members.utils.permissions import is_privileged_viewer
def can_view_personal_info(viewer, subject_member):
    """Return True if `viewer` may see `subject_member`'s personal contact info.

    If the subject has not redacted, allow. If redacted, allow only for
    privileged viewers.
    """
    if not getattr(subject_member, "redact_contact", False):
        return True
    return is_privileged_viewer(viewer)
