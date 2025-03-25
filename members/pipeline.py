# members/pipeline.py

def debug_pipeline_data(strategy, details, *args, **kwargs):
    print("🚀 OAuth details:", details)
    return

def create_username(strategy, details, backend, user=None, *args, **kwargs):
    if user:
        return

    first = details.get("first_name")
    last = details.get("last_name")

    if first and last:
        base_username = f"{first.lower()}.{last.lower()}"
    else:
        email = details.get("email", "")
        base_username = email.split('@')[0].lower()

    from django.contrib.auth import get_user_model
    User = get_user_model()

    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    # ✅ This is the key: overwrite details['username']
    details['username'] = username
    return {"username": username}

def set_default_membership_status(backend, user=None, **kwargs):
    if user and user.membership_status is None:
        user.membership_status = "Non-Member"
        user.save()

import requests
from django.core.files.base import ContentFile
from urllib.parse import urlparse
import os

def fetch_google_profile_picture(backend, user, response, *args, **kwargs):
    if backend.name == "google-oauth2":
        picture_url = response.get("picture")
        if picture_url and not user.profile_photo:
            try:
                result = requests.get(picture_url)
                result.raise_for_status()
                filename = os.path.basename(urlparse(picture_url).path)
                user.profile_photo.save(filename, ContentFile(result.content), save=True)
            except Exception as e:
                print(f"Error fetching profile photo: {e}")
