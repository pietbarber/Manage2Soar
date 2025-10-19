from typing import Optional


class AdminHelperMixin:
    """Mixin to inject a short helper message into admin changelist and change form contexts.

    Usage:
      - Define `admin_helper_message` string on your ModelAdmin.
      - Mix this class into the ModelAdmin or add the same `changelist_view` override.
    """

    admin_helper_message: Optional[str] = None
    # Optional: URL to a short admin doc for this model (relative or absolute). If set,
    # the helper fragment can render a compact 'Docs' link instead of a long inline message.
    admin_helper_doc_url: Optional[str] = None

    def _inject_helper(self, request, extra_context):
        extra_context = extra_context or {}
        if getattr(self, "admin_helper_message", None):
            extra_context["admin_helper_message"] = self.admin_helper_message
        if getattr(self, "admin_helper_doc_url", None):
            extra_context["admin_helper_doc_url"] = self.admin_helper_doc_url
        return extra_context

    def changelist_view(self, request, extra_context=None):
        extra_context = self._inject_helper(request, extra_context)
        return super().changelist_view(request, extra_context=extra_context)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        # For the edit/change form, follow the same pattern but pass into opts
        extra_context = extra_context or {}
        if getattr(self, "admin_helper_message", None):
            extra_context["admin_helper_message"] = self.admin_helper_message
        if getattr(self, "admin_helper_doc_url", None):
            extra_context["admin_helper_doc_url"] = self.admin_helper_doc_url
        return super().change_view(request, object_id, form_url, extra_context=extra_context)
