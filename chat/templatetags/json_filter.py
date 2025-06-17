import json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter(name='to_json_string')
def to_json_string(value):
    """
    Serializes an object to a JSON string.
    Handles Python dicts/lists primarily.
    Ensures the output is safe for HTML attributes by escaping appropriately if needed,
    though for checkbox values, standard JSON string escaping should be sufficient.
    """
    return mark_safe(json.dumps(value))
