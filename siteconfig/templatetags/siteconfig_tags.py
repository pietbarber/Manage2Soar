from django import template
from siteconfig.models import SiteConfiguration

register = template.Library()


@register.simple_tag
def get_siteconfig():
    return SiteConfiguration.objects.first()
