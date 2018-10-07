import functools
import pickle

import six


__all__ = (
    'pickle_dump',
    'pickle_load',
)


pickle_load_kwargs = {'encoding': 'bytes'} if six.PY3 else {}

pickle_load = functools.partial(pickle.load, **pickle_load_kwargs)
pickle_dump = functools.partial(pickle.dump, protocol=0)
