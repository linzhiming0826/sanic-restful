
def get(request):
    accept_mimetypes = request.headers.get('accept', None)
    if not accept_mimetypes:
        return []
    return str(accept_mimetypes).split(',')


def best_match(request, representations, default=None):
    if not representations:
        return default
    try:
        accept_mimetypes = get(request)
        if not accept_mimetypes:
            return default
        accept_mimetypes = [s.split(';')[0] for s in accept_mimetypes]
        for accept_type in accept_mimetypes:
            if accept_type == "*" or accept_type == "*/*" or accept_type == "*.*":
                return default
            elif accept_type in representations:
                return accept_type
    except Exception:
        return default
