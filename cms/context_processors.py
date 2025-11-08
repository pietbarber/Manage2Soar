from cms.models import HomePageContent


def footer_content(request):
    """
    Context processor to add footer content to all templates.
    Only loads footer content for authenticated users.
    """
    if request.user.is_authenticated:
        try:
            footer = HomePageContent.objects.filter(
                slug="footer", audience="member"
            ).first()
            return {"footer_content": footer}
        except Exception:
            # If CMS is not available or footer doesn't exist, fail gracefully
            return {"footer_content": None}
    else:
        return {"footer_content": None}
