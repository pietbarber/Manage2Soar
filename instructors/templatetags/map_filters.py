# instructors/templatetags/map_filters.py

from django import template

register = template.Library()


@register.filter
def get_item(dict_obj, key):
    """Lookup a dictionary value by key (returns None if missing)."""
    return dict_obj.get(key)
