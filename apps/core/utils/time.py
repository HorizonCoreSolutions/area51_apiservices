def format_time(s: int) -> str:
    h, m = divmod(s, 3600)
    m, s = divmod(m, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s and not h: parts.append(f"{s}s")
    return " ".join(parts)