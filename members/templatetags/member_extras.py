# ya know, sometimes, I don't want to construct a person's name from all these fields.
# This is a small template filter that will display a member's name in a more human-readable format.
# I wish people would be simple with a first name and a last name. Why do they have to be all difficult
# with name suffixes, and middle initials, and nicknames? 😂


from django import template

register = template.Library()

@register.filter
def display_name(member):
    parts = []

    if member.nickname:
        parts.append(f'"{member.nickname}" {member.last_name}')
    elif member.middle_initial:
        parts.append(f"{member.first_name} {member.middle_initial}. {member.last_name}")
    else:
        parts.append(f"{member.first_name} {member.last_name}")

    if member.name_suffix:
        parts.append(f", {member.name_suffix}")

    return "".join(parts)
