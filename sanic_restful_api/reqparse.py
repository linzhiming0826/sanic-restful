import collections
from copy import deepcopy
import decimal

from sanic.exceptions import abort, InvalidUsage
from sanic.request import Request, RequestParameters


class Namespace(collections.UserDict):
    def __missing__(self, name):
        raise AttributeError(name)

    def __getattr__(self, name):
        return self.__getitem__(name)


_friendly_location = {
    'json': 'the JSON body',
    'form': 'the post body',
    'args': 'the query string',
    'values': 'the post body or the query string',
    'headers': 'the HTTP headers',
    'cookies': 'the request\'s cookies',
    'files': 'an uploaded file',
}


class Argument(object):

    """
    :param name: Either a name or a list of option strings, e.g. foo or
        -f, --foo.
    :param default: The value produced if the argument is absent from the
        request.
    :param dest: The name of the attribute to be added to the object
        returned by :meth:`~reqparse.RequestParser.parse_args()`.
    :param bool required: Whether or not the argument may be omitted (optionals
        only).
    :param action: The basic type of action to be taken when this argument
        is encountered in the request. Valid options are "store" and "append".
    :param ignore: Whether to ignore cases where the argument fails type
        conversion
    :param type: The type to which the request argument should be
        converted. If a type raises an exception, the message in the
        error will be returned in the response. Defaults to :class:`unicode`
        in python2 and :class:`str` in python3.
    :param location: The attributes of the :class:`sanic.Request` object
        to source the arguments from (ex: headers, args, etc.), can be an
        iterator. The last item listed takes precedence in the result set.
    :param choices: A container of the allowable values for the argument.
    :param help: A brief description of the argument, returned in the
        response when the argument is invalid. May optionally contain
        an "{error_msg}" interpolation token, which will be replaced with
        the text of the error raised by the type converter.
    :param bool case_sensitive: Whether argument values in the request are
        case sensitive or not (this will convert all values to lowercase)
    :param bool store_missing: Whether the arguments default value should
        be stored if the argument is missing from the request.
    :param bool trim: If enabled, trims whitespace around the argument.
    :param bool nullable: If enabled, allows null value in argument.
    """

    def __init__(self,
                 name,
                 default=None,
                 dest=None,
                 required=False,
                 ignore=False,
                 type=None,
                 location=('json', 'form', 'args', 'files'),
                 choices=(),
                 action='store',
                 help=None,
                 operators=('=', ),
                 case_sensitive=True,
                 store_missing=True,
                 trim=False,
                 nullable=True,
                 ignore_invalid_usage=True):
        self.name = name
        self.default = default
        self.dest = dest
        self.required = required
        self.ignore = ignore
        self.location = location
        self.type = type
        self.choices = choices
        self.action = action
        self.help = help
        self.case_sensitive = case_sensitive
        self.operators = operators
        self.store_missing = store_missing
        self.trim = trim
        self.nullable = nullable
        self.ignore_invalid_usage = ignore_invalid_usage

    def source(self, request):
        """Pulls values off the request in the provided location
        if location is str:
            json -> dict
            form, args, file -> RequestParameters
        if location is sequence:
            return RequestParameters
        :param request: The sanic request object to parse arguments from
        """
        if isinstance(self.location, str):
            try:
                value = getattr(request, self.location, RequestParameters())
            except InvalidUsage as e:
                if self.ignore_invalid_usage:
                    return RequestParameters()
                else:
                    raise e

            if callable(value):
                value = value()
            if value:
                return value
        else:
            values = RequestParameters()
            for l in self.location:
                value = getattr(request, l, None)
                if callable(value):
                    value = value()
                if value:
                    values.update(value)
            return values

        return RequestParameters()

    def convert(self, value, op):
        if self.location == "file":
            return value
        if not value:
            if self.nullable:
                return value
            else:
                raise ValueError("Must not be null")

        try:
            if not self.type:
                return value
            return self.type(value, self.name, op)
        except TypeError:
            try:
                if self.type is decimal.Decimal:
                    return self.type(str(value), self.name)
                else:
                    return self.type(value, self.name)
            except TypeError:
                return self.type(value)

    def handle_validation_error(self, app, error, bundle_errors):
        """Called when an error is raised while parsing. Aborts the request
        with a 400 status and an error message
        :param error: the error that was raised
        :param bundle_errors: do not abort when first error occurs, return a
            dict with the name of the argument and the error message to be
            bundled
        """
        error_msg = self.help.format(error_msg=error) if self.help else error
        msg = {self.name: error_msg}

        if app.config.get("BUNDLE_ERRORS", False) or bundle_errors:
            return error, msg
        abort(400, message=msg)

    def parse(self, request, req_temp, bundle_errors=False):
        """Parses argument value(s) from the request, converting according to
        the argument's type.
        :param request: The sanic request object to parse arguments from
        :param do not abort when first error occurs, return a
            dict with the name of the argument and the error message to be
            bundled
        """
        source = self.source(request)

        results = []

        # Sentinels
        _not_found = False
        _found = True

        for operator in self.operators:
            name = self.name + operator.replace("=", "", 1)
            if name in source:
                # Account for MultiDict and regular dict
                if hasattr(source, "getlist"):
                    values = source.getlist(name)
                else:
                    values = source.get(name)
                    if not (isinstance(values, collections.MutableSequence)
                            and self.action == 'append'):
                        values = [values]

                for value in values:
                    if hasattr(value, "strip") and self.trim:
                        value = value.strip()
                    if hasattr(value, "lower") and not self.case_sensitive:
                        value = value.lower()

                        if hasattr(self.choices, "__iter__"):
                            self.choices = [choice.lower()
                                            for choice in self.choices]

                    try:
                        value = self.convert(value, operator)
                    except Exception as error:
                        if self.ignore:
                            continue
                        self.handle_validation_error(
                            request.app, error, bundle_errors)

                    if self.choices and value not in self.choices:
                        if request.app.config.get("BUNDLE_ERRORS",
                                                  False) or bundle_errors:
                            return self.handle_validation_error(
                                request.app,
                                ValueError("{0} is not a valid choice".format(
                                    value)), bundle_errors)
                        self.handle_validation_error(
                            request.app,
                            ValueError(
                                "{0} is not a valid choice".format(value)),
                            bundle_errors)

                    if name in req_temp.unparsed_arguments:
                        req_temp.unparsed_arguments.pop(name)
                    results.append(value)

        if not results and self.required:
            if isinstance(self.location, str):
                error_msg = "Missing required parameter in {0}".format(
                    _friendly_location.get(self.location, self.location)
                )
            else:
                friendly_locations = [_friendly_location.get(loc, loc)
                                      for loc in self.location]
                error_msg = "Missing required parameter in {0}".format(
                    ' or '.join(friendly_locations)
                )
            if request.app.config.get("BUNDLE_ERRORS", False) or bundle_errors:
                return self.handle_validation_error(request.app,
                                                    ValueError(error_msg),
                                                    bundle_errors)
            self.handle_validation_error(request.app, ValueError(error_msg),
                                         bundle_errors)

        if not results:
            if callable(self.default):
                return self.default(), _not_found
            else:
                return self.default, _not_found

        if self.action == 'append':
            return results, _found

        if self.action == 'store' or len(results) == 1:
            return results[0], _found
        return results, _found


class RequestParser:
    """Enables adding and parsing of multiple arguments in the context of a
    single request. Ex::
        from sanic_restful_api import reqparse
        parser = reqparse.RequestParser()
        parser.add_argument('foo')
        parser.add_argument('int_bar', type=int)
        args = parser.parse_args()
    :param bool trim: If enabled, trims whitespace on all arguments in this
        parser
    :param bool bundle_errors: If enabled, do not abort when first error
        occurs, return a dict with the name of the argument and the error
        message to be bundled and return all validation errors
    """

    def __init__(self,
                 argument_cls=Argument,
                 namespace_cls=Namespace,
                 trim=False,
                 bundle_errors=False):
        self.args = {}
        self.argument_cls = argument_cls
        self.namespace_cls = namespace_cls
        self.trim = trim
        self.bundle_errors = bundle_errors

    def add_argument(self, *args, **kwargs) -> None:
        """Adds an argument to be parsed.
        Accepts either a single instance of Argument or arguments to be passed
        into :class:`Argument`'s constructor.
        See :class:`Argument`'s constructor for documentation on the
        available options.
        """
        if len(args) == 1 and isinstance(args[0], self.argument_cls):
            # self.args[args[0].name] = args[0]
            argument_obj = args[0]
        else:
            argument_obj = self.argument_cls(*args, **kwargs)

        if self.trim and self.argument_cls is Argument:
            argument_obj.trim = kwargs.get('trim', self.trim)

        if self.args.get(argument_obj.name):
            raise RuntimeError('Argument is existed')
        else:
            self.args[argument_obj.name] = argument_obj

    def parse_args(self, request: Request, strict=False):
        """Parse all arguments from the provided request and return the results
        as a Namespace
        :param strict: if req includes args not in parser,
                throw 400 BadRequest exception
        """
        namespace = self.namespace_cls()

        # A record of arguments not yet parsed; as each is found
        # among self.args, it will be popped out
        req_temp = collections.namedtuple('RedType', 'unparsed_arguments')
        req_temp.unparsed_arguments = dict(
            self.argument_cls('').source(request)) if strict else {}
        errors = {}

        for name, arg in self.args.items():
            value, found = arg.parse(request, req_temp, self.bundle_errors)
            if isinstance(value, ValueError):
                errors.update(found)
                found = None
            if found or arg.store_missing:
                namespace[arg.dest or name] = value

        if errors:
            abort(400, message=errors)

        if strict and req_temp.unparsed_arguments:
            abort(
                400, 'Unknown arguments: %s' % ', '.join(
                    req_temp.unparsed_arguments.keys()))

        return namespace

    def copy(self):
        """
        Creates a copy of this RequestParser with
        the same set of arguments
        """
        parser_copy = self.__class__(self.argument_cls, self.namespace_cls)
        parser_copy.args = deepcopy(self.args)
        parser_copy.trim = self.trim
        parser_copy.bundle_errors = self.bundle_errors
        return parser_copy

    def replace_argument(self, name, *args, **kwargs):
        """ Replace the argument matching the given name with a new version."""
        new_args = self.argument_cls(name, *args, **kwargs)
        if self.args.get(name):
            self.args[name] = new_args
        else:
            raise AttributeError('%s not existed' % name)

    def remove_argument(self, name):
        self.args.pop(name)
