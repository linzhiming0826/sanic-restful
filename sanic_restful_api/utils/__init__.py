from werkzeug.http import HTTP_STATUS_CODES


def http_status_message(code):
    """Maps an HTTP status code to the textual status"""
    return HTTP_STATUS_CODES.get(code, '')


def unpack(value):
    """Return a three tuple of data, code, and headers"""
    if not isinstance(value, tuple):
        return value, 200, {}

    try:
        data, code, headers = value
        return data, code, headers
    except ValueError:
        pass

    try:
        data, code = value
        return data, code, {}
    except ValueError:
        pass

    return value, 200, {}


def get_accept_mimetypes(request):
    accept_types = request.headers.get('accept', None)
    if not accept_types:
        return {}
    return str(accept_types).split(',')


def best_match_accept_mimetype(request, representations, default=None):
    if not representations:
        return default
    try:
        accept_mimetypes = get_accept_mimetypes(request)
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
