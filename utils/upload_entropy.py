import os
import secrets


def upload_biography(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"biography/{name}-{token}{ext}"


def upload_profile_photo(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"profile_photos/{name}-{token}{ext}"


def upload_badge_image(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"badge_images/{name}-{token}{ext}"


def upload_written_test_media(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"written_test_media/{name}-{token}{ext}"


def upload_quals_icon(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"quals/icons/{name}-{token}{ext}"


def upload_homepage_gallery(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"homepage/gallery/{name}-{token}{ext}"


def upload_towplane_photo(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"towplane_photos/{name}-{token}{ext}"


def upload_glider_photo(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"glider_photos/{name}-{token}{ext}"


def upload_airfield_photo(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"airfield_photos/{name}-{token}{ext}"


def upload_site_logo(instance, filename):
    name, ext = os.path.splitext(filename)
    token = secrets.token_urlsafe(6)
    return f"site_logo/{name}-{token}{ext}"
