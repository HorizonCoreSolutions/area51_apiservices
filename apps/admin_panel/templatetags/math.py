from decimal import Decimal

import math

from django import template
from apps.casino.models import CasinoGameList



register = template.Library()



@register.filter(name='mult')
def mult(value, arg):
    try:
        return float(value) * float(arg)
    except:
        return value

@register.filter
def get(dictionary, key):
    return dictionary.get(key, '')


@register.filter(name='supported_device')
def supported_device(category_name, count_of="total"):
    # Check if any game in the given category supports desktop or mobile
    if count_of=="desktop":
        return CasinoGameList.objects.filter(game_category=category_name, is_desktop_supported=True).count()
    elif count_of == "mobile":
        return CasinoGameList.objects.filter(game_category=category_name, is_mobile_supported=True).count()
    else:
        return CasinoGameList.objects.filter(game_category=category_name).count()


@register.filter(name='isdigit')
def isdigit(value):
    return str(value).isdigit()

        