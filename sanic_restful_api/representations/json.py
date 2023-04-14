import orjson
from sanic.response import HTTPResponse


def output_json(app, data, code, headers=None):
    dumped = orjson.dumps(data, option=orjson.OPT_APPEND_NEWLINE)
    resp = HTTPResponse(
        dumped,
        status=code,
        content_type="application/json",
    )
    resp.headers.extend(headers or {})
    return resp
