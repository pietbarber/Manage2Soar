from django.conf import settings

from cms.models import HomePageContent


def footer_content(request):
    """
    Context processor to add footer content to all templates.
    Only loads footer content for authenticated users.
    """
    google_oauth_configured = bool(
        getattr(settings, "SOCIAL_AUTH_GOOGLE_OAUTH2_KEY", None)
    )

    if request.user.is_authenticated:
        try:
            footer = HomePageContent.objects.filter(
                slug="footer", audience="member"
            ).first()
            return {
                "footer_content": footer,
                "google_oauth_configured": google_oauth_configured,
            }
        except Exception:
            # If CMS is not available or footer doesn't exist, fail gracefully
            return {
                "footer_content": None,
                "google_oauth_configured": google_oauth_configured,
            }
    else:
        return {
            "footer_content": None,
            "google_oauth_configured": google_oauth_configured,
        }
