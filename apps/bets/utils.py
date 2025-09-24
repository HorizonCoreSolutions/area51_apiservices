import datetime


def generate_reference(user):
    now = str(datetime.datetime.now())
    return user.username + now


def validate_date(date):
    try:
        datetime.datetime.strptime(date, "%Y-%m-%d")
        return True
    except ValueError:
        return False





