from django.shortcuts import render

# Create your views here.
from django.http import HttpResponse

def roster_home(request):
    return HttpResponse("Duty Roster Home")
