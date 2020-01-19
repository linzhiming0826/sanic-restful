.. _extending:

Extending Sanic-RESTful-Api
=======================

.. currentmodule:: sanic_restful_api

We realize that everyone has different needs in a REST framework.
Sanic-RESTful-Api tries to be as flexible as possible, but sometimes you might
find that the builtin functionality is not enough to meet your needs.
Sanic-RESTful-Api has a few different extension points that can help in that case.

Content Negotiation
-------------------

Out of the box, Sanic-RESTful-Api is only configured to support JSON. We made this
decision to give API maintainers full control of over API format support; so a
year down the road you don’t have to support people using the CSV
representation of your API you didn’t even know existed. To add additional
mediatypes to your API, you’ll need to declare your supported representations
on the :class:`~Api` object. ::

    app = Sanic(__name__)
    api = Api(app)

    @api.representation('application/json')
    def output_json(data, code, headers=None):
        resp = make_response(json.dumps(data), code)
        resp.headers.extend(headers or {})
        return resp

These representation functions must return a Sanic :class:`~sanic.Response`
object.

.. Note ::

    Sanic-RESTful-Api uses the :mod:`json` module from the Python standard library
    instead of :mod:`sanic.json` because the Sanic JSON serializer includes
    serialization capabilities which are not in the JSON spec. If your
    application needs these customizations, you can replace the default JSON
    representation with one using the Sanic JSON module as described above.

It is possible to configure how the default Sanic-RESTful-Api JSON representation
will format JSON by providing a ``RESTFUL_JSON`` attribute on the application
configuration. This setting is a dictionary with keys that correspond to the
keyword arguments of :py:func:`json.dumps`. ::

    class MyConfig(object):
        RESTFUL_JSON = {'separators': (', ', ': '),
                        'indent': 2,
                        'cls': MyCustomEncoder}

.. Note ::

    If the application is running in debug mode (``app.debug = True``) and
    either ``sort_keys`` or ``indent`` are not declared in the ``RESTFUL_JSON``
    configuration setting, Sanic-RESTful will provide defaults of ``True`` and
    ``4`` respectively.

Custom Fields & Inputs
----------------------

One of the most common additions to Sanic-RESTful-Api is to define custom types or
fields based on your own data types.

Fields
~~~~~~

Custom output fields let you perform your own output formatting without having
to modify your internal objects directly. All you have to do is subclass
:class:`~fields.Raw` and implement the :meth:`~fields.Raw.format` method::

    class AllCapsString(fields.Raw):
        def format(self, value):
            return value.upper()


    # example usage
    fields = {
        'name': fields.String,
        'all_caps_name': AllCapsString(attribute=name),
    }

Inputs
~~~~~~

For parsing arguments, you might want to perform custom validation.  Creating
your own input types lets you extend request parsing with ease. ::

    def odd_number(value):
        if value % 2 == 0:
            raise ValueError("Value is not odd")

        return value

The request parser will also give you access to the name of the argument for
cases where you want to reference the name in the error message. ::

    def odd_number(value, name):
        if value % 2 == 0:
            raise ValueError("The parameter '{}' is not odd. You gave us the value: {}".format(name, value))

        return value

You can also convert public parameter values to internal representations: ::

    # maps the strings to their internal integer representation
    # 'init' => 0
    # 'in-progress' => 1
    # 'completed' => 2

    def task_status(value):
        statuses = [u"init", u"in-progress", u"completed"]
        return statuses.index(value)


Then you can use these custom input types in your
:class:`~reqparse.RequestParser`: ::

    parser = reqparse.RequestParser()
    parser.add_argument('OddNumber', type=odd_number)
    parser.add_argument('Status', type=task_status)
    args = parser.parse_args()


Response Formats
----------------

To support other representations (xml, csv, html), you can use the
:meth:`~Api.representation` decorator.  You need to have a reference to your
API. ::

    api = Api(app)

    @api.representation('text/csv')
    def output_csv(data, code, headers=None):
        pass
        # implement csv output!

These output functions take three parameters, ``data``, ``code``, and
``headers``

``data`` is the object you return from your resource method, code is the HTTP
status code that it expects, and headers are any HTTP headers to set in the
response. Your output function should return a :class:`sanic.Response` object. ::

    def output_json(data, code, headers=None):
        """Makes a Sanic response with a JSON encoded body"""
        resp = make_response(json.dumps(data), code)
        resp.headers.extend(headers or {})
        return resp

Another way to accomplish this is to subclass the :class:`~Api` class and
provide your own output functions. ::

    class Api(restful.Api):
        def __init__(self, *args, **kwargs):
            super(Api, self).__init__(*args, **kwargs)
            self.representations = {
                'application/xml': output_xml,
                'text/html': output_html,
                'text/csv': output_csv,
                'application/json': output_json,
            }

Resource Method Decorators
--------------------------

There is a property on the :class:`~sanic_restful_api.Resource` class called
``method_decorators``. You can subclass the Resource and add your own
decorators that will be added to all ``method`` functions in resource. For
instance, if you want to build custom authentication into every request. ::

    def authenticate(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not getattr(func, 'authenticated', True):
                return func(*args, **kwargs)

            acct = basic_authentication()  # custom account lookup function

            if acct:
                return func(*args, **kwargs)

            sanic_restful_api.abort(401)
        return wrapper


    class Resource(sanic_restful_api.Resource):
        method_decorators = [authenticate]   # applies to all inherited resources

Alternatively, you can specify a dictionary of iterables that map to HTTP methods
and the decorators will only apply to matching requests.

.. code-block:: python

    def cache(f):
        @wraps(f)
        def cacher(*args, **kwargs):
            # caching stuff
        return cacher

    class MyResource(restful.Resource):
        method_decorators = {'get': [cache]}

         def get(self, *args, **kwargs):
            return something_interesting(*args, **kwargs)

         def post(self, *args, **kwargs):
            return create_something(*args, **kwargs)

In this case, the caching decorator would only apply to the `GET` request and not
the `POST` request.

Since Sanic-RESTful-Api Resources are actually Sanic view objects.

Custom Error Handlers
---------------------

Error handling is a tricky problem. Your Sanic application may be wearing
multiple hats, yet you want to handle all Sanic-RESTful-Api errors with the correct
content type and error syntax as your 200-level requests.

Sanic-RESTful will call the :meth:`~sanic_restful_api.Api.handle_error`
function on any 400 or 500 error that happens on a Sanic-RESTful route, and
leave other routes alone. You may want your app to return an error message with
the correct media type on 404 Not Found errors; in which case, use the
`catch_all_404s` parameter of the :class:`~sanic_restful.Api` constructor. ::

    app = Sanic(__name__)
    api = sanic_restful_api.Api(app, catch_all_404s=True)

Then Sanic-RESTful will handle 404s in addition to errors on its own routes.

Sometimes you want to do something special when an error occurs - log to a
file, send an email, etc. Use the :meth:`~sanic.got_request_exception` method
to attach custom error handlers to an exception. ::

    def log_exception(sender, exception, **extra):
        """ Log an exception to our logging framework """
        sender.logger.debug('Got exception during processing: %s', exception)

    from sanic import got_request_exception
    got_request_exception.connect(log_exception, app)

Define Custom Error Messages
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
You may want to return a specific message and/or status code when certain errors
are encountered during a request. You can tell Sanic-RESTful how you want to
handle each error/exception so you won't have to fill your API code with
try/except blocks. ::

    errors = {
        'UserAlreadyExistsError': {
            'message': "A user with that username already exists.",
            'status': 409,
        },
        'ResourceDoesNotExist': {
            'message': "A resource with that ID no longer exists.",
            'status': 410,
            'extra': "Any extra information you want.",
        },
    }

Including the `'status'` key will set the Response's status code. If not
specified it will default to 500.

Once your ``errors`` dictionary is defined, simply pass it to the
:class:`~sanic_restful.Api` constructor. ::

    app = Sanic(__name__)
    api = sanic_restful_api.Api(app, errors=errors)

Note: Custom `Exceptions` must have  :class:`~werkzeug.exceptions.HTTPException` as the base Exception.
