# analytics/templatetags/json_script.py
from django import template
from django.utils.html import json_script as _json_script

register = template.Library()

@register.filter(name="json_script")
def json_script_filter(value, element_id):
    """
    Safe <script type="application/json" id="...">...</script> output
    so you can JSON.parse() it in JS without escaping headaches.
    """
    return _json_script(value, element_id)
