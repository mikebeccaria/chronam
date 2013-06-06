from django import template
from django.template.defaultfilters import stringfilter
from django.utils.text import normalize_newlines
from django.utils.html import (conditional_escape, escapejs, fix_ampersands,
    escape, urlize as urlize_impl, linebreaks, strip_tags)
from django.utils.safestring import mark_safe, SafeData, mark_for_escaping
from rfc3339 import rfc3339

from chronam.core.utils import url
from chronam.core.utils.utils import label



register = template.Library()

@register.filter(name='rfc3339')
def rfc3339_filter(d):
    return rfc3339(d)

@register.filter(name='pack_url')
def pack_url(value, default='-'):
    return url.pack_url_path(value, default)

@register.filter(name='label')
def _label(value):
    return label(value)

@register.filter("removelinebreaks", is_safe=True, needs_autoescape=True)
@stringfilter
def linebreaksbr(value, autoescape=None):
    """
    Converts all newlines in a piece of plain text to HTML line breaks
    (``<br />``).
    """
    autoescape = autoescape and not isinstance(value, SafeData)
    value = normalize_newlines(value)
    if autoescape:
        value = escape(value)
    return mark_safe(value.replace('\n', ' '))
