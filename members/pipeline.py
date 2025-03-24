# members/pipeline.py

def create_username(strategy, details, backend, user=None, *args, **kwargs):
    """
    Set username to "firstname.lastname" on first-time Google login.
    """
    if user:
        return

    first = details.get("first_name", "").lower()
    last = details.get("last_name", "").lower()

    if first and last:
        desired_username = f"{first}.{last}"
    else:
        desired_username = details.get("email").split("@")[0]

    # Ensure uniqueness
    from django.contrib.auth import get_user_model
    User = get_user_model()
    original = desired_username
    counter = 1
    while User.objects.filter(username=desired_username).exists():
        desired_username = f"{original}{counter}"
        counter += 1

    return {"username": desired_username}
