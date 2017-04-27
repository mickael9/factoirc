import traceback
import functools
from .irc_colors import IRCColors


def catch(f):
    @functools.wraps(f)
    async def wrap(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except Exception as ex:
            return '{c.boldRed}Error:{c.boldDefault} {error}'.format(
                    error=traceback.format_exception_only(type(ex), ex)[0],
                    c=IRCColors)
    return wrap
