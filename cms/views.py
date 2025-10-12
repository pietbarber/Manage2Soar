from django.shortcuts import render
from cms.models import HomePageContent
from django.shortcuts import redirect


def homepage(request):
    user = request.user
    allowed_statuses = [
        "Full Member", "Student Member", "Family Member", "Service Member",
        "Founding Member", "Honorary Member", "Emeritus Member",
        "SSEF Member", "Temporary Member", "Introductory Member"
    ]
    if user.is_authenticated and (
        user.is_superuser or getattr(
            user, "membership_status", None) in allowed_statuses
    ):
        page = HomePageContent.objects.filter(
            audience='member', slug='member-home').first()
    else:
        page = HomePageContent.objects.filter(
            audience='public', slug='home').first()
    return render(request, 'cms/homepage.html', {'page': page})

# Create your views here.
