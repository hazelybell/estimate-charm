import inspect
from optparse import OptionParser


class UserError(Exception):
    pass


def add_dict(name, **kwargs):
    """Decorator to add a named dictionary to a function's attributes.

    The kwargs are the contents of the dict.
    :param name: The name of the dictionary to add.
    """
    def decorator(func):
        setattr(func, name, kwargs)
        return func
    return decorator


def types(**kwargs):
    """Declare the types require by the arguments of a function.

    The kwargs are the values to set, as used by OptionParser.add_option::
      @types(port="int", delay=int)
    """
    return add_dict('_types', **kwargs)


def helps(**kwargs):
    """Declare the help for the arguments of a function.

    The kwargs are used to assign help::
      helps(port="The port to use.", delay="The time to wait.")
    """
    return add_dict('_helps', **kwargs)


def get_function_parser(function):
    """Generate an OptionParser for a function.

    Option names are derived from the parameter names.  Defaults come from the
    parameter defaults.  Types are inferred from the default, or may be
    specified using the types decorator.  Per-option help may be specified
    using the helps decorator.

    :param function: The function to generate a parser for.
    """
    parser = OptionParser()
    args, ignore, ignored, defaults = inspect.getargspec(function)
    if defaults is None:
        defaults = [None] * len(args)
    arg_types = getattr(function, '_types', {})
    arg_helps = getattr(function, '_helps', {})
    for arg, default in zip(args, defaults):
        arg_type = arg_types.get(arg)
        if arg_type is None:
            if default is None:
                continue
            arg_type = type(default)
        arg_help = arg_helps.get(arg)
        if arg_help is not None:
            arg_help += ' Default: %default.'
        parser.add_option(
            '--%s' % arg, type=arg_type, help=arg_help, default=default)
    return parser


def parse_args(command, args):
    """Return the positional arguments as a dict.

    :param command: A function to treat as a command.
    :param args: The positional arguments supplied to that function.
    :return: A dict mapping variable names to arguments.
    """
    # TODO: implement!
    # Basically each argument without a default is treated as a positional
    # argument.  They must have types defined, since we can't infer it from
    # the default.
    #
    # We may wish to declare optional positional arguments.  These would have
    # have defaults, but declaring them as positional would prevent them from
    # being treated as flags.
    if len(args) != 0:
        raise UserError('Too many arguments.')
    return {}


def run_from_args(command, cmd_args):
    """Run a command function using the specified commandline arguments.

    :param command: A function to treat as a command.
    :param cmd_args: The commandline arguments to use to run the command.
    """
    parser = get_function_parser(command)
    options, args = parser.parse_args(cmd_args)
    kwargs = parse_args(command, args)
    kwargs.update(options.__dict__)
    command(**kwargs)


def run_subcommand(subcommands, argv):
    """Run a subcommand as specified by argv.

    :param subcommands: A dict mapping subcommand names to functions.
    :param argv: The arguments supplied by the user.  argv[0] should be the
        subcommand name.
    """
    if len(argv) < 1:
        raise UserError('Must supply a command: %s.' %
                        ', '.join(subcommands.keys()))
    try:
        command = subcommands[argv[0]]
    except KeyError:
        raise UserError('%s invalid.  Valid commands: %s.' %
                        (argv[0], ', '.join(subcommands.keys())))
    run_from_args(command, argv[1:])
