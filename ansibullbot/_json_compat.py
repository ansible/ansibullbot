from __future__ import absolute_import, division, print_function

from functools import partial
import json

from ._text_compat import to_text


__all__ = 'json_dump', 'json_dumps'


_to_surrogate_text = partial(to_text, errors='surrogate_or_strict')


class JSONUnicodeEncoder(json.JSONEncoder):
    """JSON encoder honoring unicode strings."""

    def iterencode(self, o, *args, **kwargs):
        """Emit unicode chunks when writing to file."""
        def noop(v): return v
        transformer = noop if self.ensure_ascii else _to_surrogate_text

        return (
            transformer(chunk)
            for chunk in super(JSONUnicodeEncoder, self).iterencode(o, *args, **kwargs)
        )


_json_compat_kwargs = {
    'cls': JSONUnicodeEncoder,
    'ensure_ascii': False,
    'indent': 2,
    'sort_keys': True,
}


json_dump = partial(json.dump, **_json_compat_kwargs)
json_dumps = partial(json.dumps, **_json_compat_kwargs)
