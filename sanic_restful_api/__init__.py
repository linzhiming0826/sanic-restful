from __future__ import absolute_import
from functools import wraps
from sanic.request import Request
from sanic.exceptions import abort as original_sanic_abort
from sanic.views import HTTPMethodView
from werkzeug.exceptions import NotAcceptable
from sanic_restful_api.utils import unpack, accept_mimetypes
from sanic_restful_api.representations.json import output_json
from collections import OrderedDict
from sanic import Blueprint, Sanic
from sanic.exceptions import ServerError
from sanic.response import BaseHTTPResponse, text
from werkzeug.http import parse_accept_header
try:
    from collections.abc import Mapping
except ImportError:
    from collections import Mapping

__all__ = ('Api', 'Resource', 'marshal', 'marshal_with',
           'marshal_with_field', 'abort')


def abort(http_status_code, message=None):
    """Raise a HTTPException for the given http_status_code. Attach a message to the exception for later processing.
    """
    original_sanic_abort(http_status_code, message)


DEFAULT_REPRESENTATIONS = [('application/json', output_json)]


class Api(object):
    """
    The main entry point for the application.
    You need to initialize it with a Sanic Application: ::
    >>> app = Sanic(__name__)
    >>> api = restful.Api(app)
    Alternatively, you can use :meth:`init_app` to set the Sanic application
    after it has been constructed.
    :param app: the Sanic application object
    :type app: sanic.Sanic or sanic.Blueprint
    :param prefix: Prefix all routes with a value, eg v1 or 2010-04-01
    :type prefix: str
    :param default_mediatype: The default media type to return
    :type default_mediatype: str
    :param decorators: Decorators to attach to every resource
    :type decorators: list
    :param url_part_order: A string that controls the order that the pieces
        of the url are concatenated when the full url is constructed.  'b'
        is the blueprint (or blueprint registration) prefix, 'a' is the api
        prefix, and 'e' is the path component the endpoint is added with
    """

    def __init__(self,
                 app=None,
                 prefix='',
                 default_mediatype="application/json",
                 decorators=None,
                 url_part_order="bae"):
        self.representations = OrderedDict(DEFAULT_REPRESENTATIONS)
        self.urls = {}
        self.prefix = prefix
        self.default_mediatype = default_mediatype
        self.decorators = decorators if decorators else []
        self.url_part_order = url_part_order
        self.endpoints = set()
        self.resources = []
        self.app = None
        self.blueprint = None

        if app:
            self.app = app
            self.init_app(app)

    def init_app(self, app):
        """Initialize this class with the given :class:`sanic.Sanic`
        application or :class:`sanic.Blueprint` object.
        :param app: the Sanic application or blueprint object
        Examples::
            api = Api()
            api.add_resource(...)
            api.init_app(app)
        """
        if isinstance(app, Blueprint):
            self.blueprint = app
            self._bp_register = app.register
            app.register = self._sanic_blueprint_register_hook(app)
        elif isinstance(app, Sanic):
            self.register_api(app)
        else:
            raise TypeError("only support sanic object and blupirint")

    def _sanic_blueprint_register_hook(self, bp: Blueprint):
        def register(app, options):
            bp_obj = self._bp_register(app, options)
            self.register_api(bp)
            return bp_obj
        return register

    def register_api(self, app):
        if len(self.resources) > 0:
            for resource, urls, kwargs in self.resources:
                self._register_view(app, resource, *urls, **kwargs)

    def _register_view(self, app, resource, *urls, **kwargs):
        endpoint = kwargs.pop("endpoint", None) or resource.__name__.lower()
        self.endpoints.add(endpoint)
        resource_class_args = kwargs.pop("resource_class_args", ())
        resource_class_kwargs = kwargs.pop("resource_class_kwargs", {})

        resource.mediatypes = self.mediatypes
        resource.endpoint = endpoint
        resource_func = self.output(
            resource.as_view(self, *resource_class_args,
                             **resource_class_kwargs))

        for decorator in self.decorators:
            resource_func = decorator(resource_func)

        for url in urls:
            rule = self._complete_url(url, '')
            # Add the url to the application or blueprint
            app.add_route(uri=rule, handler=resource_func, **kwargs)

    @property
    def mediatypes(self):
        return [
            "application/json",
            "text/plain; charset=utf-8",
            "application/octet-stream",
            "text/html; charset=utf-8",
        ]

    def output(self, resource):
        """Wraps a resource (as a sanic view function), for cases where the
        resource does not directly return a response object
        :param resource: The resource as a sanic view function
        """
        @wraps(resource)
        async def wrapper(request, *args, **kwargs):
            resp = await resource(request, *args, **kwargs)
            if isinstance(resp, BaseHTTPResponse):
                return resp
            else:
                data, code, headers = unpack(resp)
            return self.make_response(request, data, code, headers=headers)
        return wrapper

    def make_response(self, request, data, *args, **kwargs):
        """Looks up the representation transformer for the requested media
        type, invoking the transformer to create a response object. This
        defaults to default_mediatype if no transformer is found for the
        requested mediatype. If default_mediatype is None, a 406 Not
        Acceptable response will be sent as per RFC 2616 section 14.1
        :param data: Python object containing response data to be transformed
        """
        default_mediatype = kwargs.pop("fallback_mediatype",
                                       None) or self.default_mediatype
        mediatype = parse_accept_header(request.headers.get(
            'accept', None)).best_match(
                self.representations, default=default_mediatype)
        if not mediatype:
            raise NotAcceptable("Not Acceptable")
        if mediatype in self.representations:
            resp = self.representations[mediatype](request.app, data, *args,
                                                   **kwargs)
            resp.headers["Content-type"] = mediatype
            return resp
        elif mediatype == "text/plain":
            resp = text(str(data), *args, **kwargs)
            return resp
        else:
            raise ServerError(None)

    def _complete_url(self, url_part, registration_prefix):
        """This method is used to defer the construction of the final url in
        the case that the Api is created with a Blueprint.
        :param url_part: The part of the url the endpoint is registered with
        :param registration_prefix: The part of the url contributed by the
            blueprint.  Generally speaking, BlueprintSetupState.url_prefix
        """
        parts = {'b': registration_prefix, 'a': self.prefix, 'e': url_part}
        return ''.join(parts[key] for key in self.url_part_order if parts[key])

    def add_resource(self, resource, *urls, **kwargs):
        """Adds a resource to the api.
        :param resource: the class name of your resource
        :type resource: :class:`Resource`
        :param urls: one or more url routes to match for the resource, standard
                     sanic routing rules apply.  Any url variables will be
                     passed to the resource method as args.
        :type urls: str
        :param endpoint: endpoint name
            (defaults to :meth:`Resource.__name__.lower`
            Can be used to reference this route in :class:`fields.Url` fields
        :type endpoint: str
        :param resource_class_args: args to be forwarded to the constructor of
            the resource.
        :type resource_class_args: tuple
        :param resource_class_kwargs: kwargs to be forwarded to the constructor
            of the resource.
        :type resource_class_kwargs: dict
        Additional keyword arguments not specified above will be passed as-is
        to :meth:`sanic.Sanic.add_url_rule`.
        Examples::
            api.add_resource(HelloWorld, '/', '/hello')
            api.add_resource(Foo, '/foo', endpoint="foo")
            api.add_resource(FooSpecial, '/special/foo', endpoint="foo")
        """
        if self.app:
            self._register_view(self.app, resource, *urls, **kwargs)
        else:
            self.resources.append((resource, urls, kwargs))

    def resource(self, *urls, **kwargs):
        """Wraps a :class:`~sanic_restful_api.Resource` class, adding it to the
        api. Parameters are the same as :meth:`~sanic_restful_api.Api.add_resource`
        Example::
            app = Sanic(__name__)
            api = restful.Api(app)
            @api.resource('/foo')
            class Foo(Resource):
                def get(self):
                    return 'Hello, World!'
        """

        def decorator(cls):
            self.add_resource(cls, *urls, **kwargs)
            return cls

        return decorator

    def representation(self, mediatype):
        """Allows additional representation transformers to be declared for the
        api. Transformers are functions that must be decorated with this
        method, passing the mediatype the transformer represents. Three
        arguments are passed to the transformer:
        * The data to be represented in the response body
        * The http status code
        * A dictionary of headers
        The transformer should convert the data appropriately for the mediatype
        and return a Sanic response object.
        Ex::
            @api.representation('application/xml')
            def xml(data, code, headers):
                resp = make_response(convert_data_to_xml(data), code)
                resp.headers.extend(headers)
                return resp
        """

        def wrapper(func):
            self.representations[mediatype] = func
            return func

        return wrapper


class Resource(HTTPMethodView):
    """
    Represents an abstract RESTful resource. Concrete resources should
    extend from this class and expose methods for each supported HTTP
    method. If a resource is invoked with an unsupported HTTP method,
    the API will return a response with status 405 Method Not Allowed.
    Otherwise the appropriate method is called and passed all arguments
    from the url rule used when adding the resource to an Api instance. See
    :meth:`~sanic_restful_api.Api.add_resource` for details.
    :param method_decorators: Mapping class; if you need use Sequence,
        use decorators attribute.
        example:
            method_decorators = {'get': login_require}
            method_decoratros = {'get': [permission, login_require]}
    """
    representations = None
    method_decorators = []

    def __init__(self, request: Request, *args, **kwargs):
        self.request = request

    async def dispatch_request(self, request: Request, *args, **kwargs):
        meth = getattr(self, request.method.lower(), None)
        if meth is None and request.method == 'HEAD':
            meth = getattr(self, 'get', None)
        assert meth is not None, 'Unimplemented method %r' % request.method

        if isinstance(self.method_decorators, Mapping):
            decorators = self.method_decorators.get(request.method.lower(), [])
        else:
            decorators = self.method_decorators

        for decorator in decorators:
            meth = decorator(meth)

        resp = await meth(request, *args, **kwargs)
        if isinstance(resp, BaseHTTPResponse):
            return resp

        representations = self.representations or OrderedDict()
        mediatype = accept_mimetypes.best_match(
            request, representations, default=None)
        if mediatype in representations:
            data, code, headers = unpack(resp)
            resp = representations[mediatype](data, code, headers)
            resp.headers['Content-Type'] = mediatype
        return resp


def marshal(data, fields, envelope=None):
    """Takes raw data (in the form of a dict, list, object) and a dict of
    fields to output and filters the data based on those fields.
    :param data: the actual object(s) from which the fields are taken from
    :param fields: a dict of whose keys will make up the final serialized
                   response output
    :param envelope: optional key that will be used to envelop the serialized
                     response
    >>> from sanic_restful_api import fields, marshal
    >>> data = { 'a': 100, 'b': 'foo' }
    >>> mfields = { 'a': fields.Raw }
    >>> marshal(data, mfields)
    OrderedDict([('a', 100)])
    >>> marshal(data, mfields, envelope='data')
    OrderedDict([('data', OrderedDict([('a', 100)]))])
    """

    def make(cls):
        if isinstance(cls, type):
            return cls()
        return cls

    if isinstance(data, (list, tuple)):
        return (OrderedDict([(envelope, [marshal(d, fields) for d in data])])
                if envelope else [marshal(d, fields) for d in data])

    items = ((k, marshal(data, v)
              if isinstance(v, dict) else make(v).output(k, data))
             for k, v in fields.items())
    return OrderedDict(
        [(envelope, OrderedDict(items))]) if envelope else OrderedDict(items)


class marshal_with(object):
    """A decorator that apply marshalling to the return values of your methods.
    >>> from sanic_restful_api import fields, marshal_with
    >>> mfields = { 'a': fields.Raw }
    >>> @marshal_with(mfields)
    ... def get():
    ...     return { 'a': 100, 'b': 'foo' }
    ...
    ...
    >>> get()
    OrderedDict([('a', 100)])
    >>> @marshal_with(mfields, envelope='data')
    ... def get():
    ...     return { 'a': 100, 'b': 'foo' }
    ...
    ...
    >>> get()
    OrderedDict([('data', OrderedDict([('a', 100)]))])
    see :meth:`sanic_restful_api.marshal`
    """

    def __init__(self, fields, envelope=None):
        """
        :param fields: a dict of whose keys will make up the final
                       serialized response output
        :param envelope: optional key that will be used to envelop the
                        serialized response
        """
        self.fields = fields
        self.envelope = envelope

    def __call__(self, f):
        @wraps(f)
        async def wrapper(*args, **kwargs):
            _cls = args[0] if args else None
            if isinstance(_cls, Resource):
                pass
            resp = await f(*args, **kwargs)
            if isinstance(resp, tuple):
                data, code, headers = unpack(resp)
                return marshal(data, self.fields, self.envelope), code, headers
            else:
                return marshal(resp, self.fields, self.envelope)

        return wrapper


class marshal_with_field(object):
    """
    A decorator that formats the return values of your methods
     with a single field.
    >>> from sanic_restful_api import marshal_with_field, fields
    >>> @marshal_with_field(fields.List(fields.Integer))
    ... def get():
    ...     return ['1', 2, 3.0]
    ...
    >>> get()
    [1, 2, 3]
    see :meth:`sanic_restful_api.marshal_with`
    """

    def __init__(self, field):
        """
        :param field: a single field with which to marshal the output.
        """
        if isinstance(field, type):
            self.field = field()
        else:
            self.field = field

    def __call__(self, f):
        @wraps(f)
        async def wrapper(*args, **kwargs):
            resp = await f(*args, **kwargs)
            if isinstance(resp, tuple):
                data, code, headers = unpack(resp)
                return self.field.format(data), code, headers
            return self.field.format(resp)

        return wrapper
