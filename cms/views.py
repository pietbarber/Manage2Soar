
from django.shortcuts import render
from cms.models import HomePageContent


def homepage(request):
    if request.user.is_authenticated:
        page = HomePageContent.objects.filter(
            audience='member', slug='member-home').first()
    else:
        page = HomePageContent.objects.filter(
            audience='public', slug='home').first()
    return render(request, 'cms/homepage.html', {'page': page})

# Create your views here.
