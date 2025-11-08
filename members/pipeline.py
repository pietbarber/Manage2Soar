import os
import re
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile

#########################
# debug_pipeline_data() Pipeline Function

# Debug utility that prints out the 'details' dictionary received from the
# OAuth2 provider during the social-auth pipeline. This is useful during
# development to inspect what user data (e.g., name, email, picture) is
# being returned by the identity provider.

# Parameters:
# - strategy: the current pipeline strategy object
# - details: dictionary of user info (email, name, picture, etc.)
# - *args, **kwargs: standard pipeline context

# Note:
# Should be removed or disabled in production to avoid printing sensitive data.


def debug_pipeline_data(strategy, details, *args, **kwargs):
    if settings.DEBUG:
        print("🚀 OAuth details:", details)


########################
# create_username
# Generates a clean, unique username during social-auth pipeline execution.
#
# Combines first name, last name (or nickname), strips invalid characters,
# and falls back to email prefix if names are missing.
#
# Overwrites details['username'] and returns it for downstream use.


def create_username(strategy, details, backend, user=None, *args, **kwargs):
    if user:
        return  # User already exists, nothing to do

    nickname = details.get("nickname") or None
    first = details.get("first_name") or ""
    last = details.get("last_name") or ""
    email = details.get("email", "")

    # Prefer nickname if available
    raw_first = nickname or first
    raw_last = last

    # Strip non-alpha characters and normalize to lowercase
    first_clean = re.sub(r"[^A-Za-z]", "", raw_first).lower()
    last_clean = re.sub(r"[^A-Za-z]", "", raw_last).lower()

    if first_clean and last_clean:
        base_username = f"{first_clean}.{last_clean}"
    elif email:
        base_username = email.split("@")[0].lower()
        base_username = re.sub(r"[^a-z0-9]", "", base_username)
    else:
        base_username = "user"

    User = get_user_model()
    username = base_username
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{base_username}{counter}"
        counter += 1

    details["username"] = username
    return {"username": username}


#########################
# set_default_membership_status() Pipeline Function

# This function assigns a default membership_status of "Pending" to any newly
# created user via social-auth (e.g., Google login). This signals to the
# membership team that the user authenticated successfully and is awaiting
# review or manual approval.

# This prevents users from defaulting to full member access, and provides
# a clean, typo-free base profile for further editing.


def set_default_membership_status(strategy, user, *args, **kwargs):
    if not user.membership_status or user.membership_status.strip() == "":
        user.membership_status = "Pending"


#########################
# fetch_google_profile_picture() Pipeline Function

# Downloads and stores the user's Google profile photo the first time they log in
# using OAuth2. This eliminates the need for the user to manually upload a photo.

# Conditions:
# - Only runs if the user has no existing profile_photo
# - Only triggers for the 'google-oauth2' backend
# - Grabs the photo URL from the OAuth response payload
# - Saves the photo to media/profile_photos/<username>.jpg

# Parameters:
# - backend: the OAuth2 backend (should be 'google-oauth2')
# - user: the Django Member object created or logged in
# - response: the full OAuth2 JSON payload (contains 'picture' field)

# Notes:
# - If the image cannot be downloaded or saved, the function silently fails
#   and does not raise an exception (login still succeeds).


def fetch_google_profile_picture(backend, user, response, *args, **kwargs):
    if backend.name == "google-oauth2":
        picture_url = response.get("picture")
        if picture_url and not user.profile_photo:
            try:
                # Add timeout to prevent hanging requests
                result = requests.get(picture_url, timeout=10)
                result.raise_for_status()
                filename = os.path.basename(urlparse(picture_url).path)
                user.profile_photo.save(
                    filename, ContentFile(result.content), save=True
                )
            except Exception as e:
                print(f"Error fetching profile photo: {e}")
