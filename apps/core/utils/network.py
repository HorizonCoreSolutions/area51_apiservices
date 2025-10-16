import time

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

def get_user_ip_from_request(request) -> str:
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()  # client’s real IP
        # data = [x_forwarded_for]
    else:
        ip = request.META.get('REMOTE_ADDR')
        # data = [ip]
    # ip = data[0]
    return ip