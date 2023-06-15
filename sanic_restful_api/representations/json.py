import orjson
from sanic.response import HTTPResponse


def output_json(app, data, code, headers=None):
    settings = app.config.get(
        'RESTFUL_JSON', orjson.OPT_APPEND_NEWLINE | orjson.OPT_NON_STR_KEYS)
    dumped = orjson.dumps(data, option=settings)
    resp = HTTPResponse(
        dumped,
        status=code,
        content_type="application/json",
    )
    resp.headers.extend(headers or {})
    return resp
