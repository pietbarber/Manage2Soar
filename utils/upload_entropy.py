import os
import secrets


def upload_with_entropy(subfolder):
    def wrapper(instance, filename):
        name, ext = os.path.splitext(filename)
        token = secrets.token_urlsafe(6)
        return f"{subfolder}/{name}-{token}{ext}"
    return wrapper
