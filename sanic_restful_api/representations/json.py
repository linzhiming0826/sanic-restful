from sanic.response import HTTPResponse
from ujson import dumps


def output_json(app, data, code, headers=None):
    settings = app.config.get('RESTFUL_JSON', {})
    if app.debug:
        settings.setdefault('indent', 4)
    dumped = dumps(data, **settings) + "\n"
    resp = HTTPResponse(
        dumped,
        status=code,
        content_type="application/json",
    )
    resp.headers.extend(headers or {})
    return resp
