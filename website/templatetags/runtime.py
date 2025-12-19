from django import template

register = template.Library()


@register.filter
def runtime_format(minutes):
    minutes = int(minutes)
    hours = minutes // 60
    rem = minutes % 60
    if hours and rem:
        return f"{hours}h {rem}m"
    if hours:
        return f"{hours}h"
    return f"{rem}m"
