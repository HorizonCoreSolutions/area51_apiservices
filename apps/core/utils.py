import os
import time

from django.core.exceptions import ImproperlyConfigured


def get_env_var(var_name, default=None):
    try:
        return os.environ.get(var_name, default)
    except KeyError:
        error_msg = "Set the %s environment variable" % var_name
        raise ImproperlyConfigured(error_msg)


def save_request(service:str, request, is_response=False):
    file = f"{service}.txt"
    ts = str(time.time())
    full_url = request.build_absolute_uri() if not is_response else "response:"
    from pprint import pformat
    data = pformat(request.data) if not is_response else pformat(request)

    entry = (
        f"\n--- {ts} ---\n"
        f"URL: {full_url}\n"
        f"DATA:\n{data}\n"
    )

    with open(file, 'a') as f:
        f.write(entry)