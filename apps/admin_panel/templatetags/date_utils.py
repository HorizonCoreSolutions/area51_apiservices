from datetime import timedelta,datetime,timezone

from django import template
import pytz

register = template.Library()


@register.filter(name='local_date')
def local_date(value, arg):
    if arg:
        arg = int(arg)
        return value + timedelta(minutes=arg)
    return value

@register.filter(name="est_to_utc")
def est_to_utc(datetime_str):
    if datetime_str:
        datetime_str = datetime_str.replace(tzinfo=timezone.utc).strftime("%d/%m/%Y %H:%M")
        return datetime_str
    return None

@register.filter(name='dob_date')
def dob_date(value):
    if value:
        return value[:10]
    return value


@register.filter(name='get_json')
def dob_date(value):
    import json
    return json.dumps(value)


@register.filter(name='to_local_timezone')
def to_local_timezone(date, users_timezone):
    print("date", date)
    if users_timezone:
        tz = pytz.timezone(users_timezone)
        localized_dt = date.astimezone(tz).strftime("%B %d, %Y, %I:%M %p")
        print("localized_dt", localized_dt)
        return localized_dt
    else:
        return date
    
    