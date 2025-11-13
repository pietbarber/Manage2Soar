from django import template
from django.forms import BoundField

register = template.Library()


@register.filter
def dict_get(d, key):
    return d.get(key, "")


@register.filter
def add_class(field, css_classes):
    """
    Add CSS classes to a form field.
    Usage: {{ form.field|add_class:"form-control" }}
    """
    if isinstance(field, BoundField):
        return field.as_widget(attrs={"class": css_classes})
    return field
