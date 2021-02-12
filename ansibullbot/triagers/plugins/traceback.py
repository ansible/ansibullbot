import re


RE_FILE_LINE = r'file "(.*)", line \d+, in'


def get_traceback_facts(iw):
    tfacts = {
        'has_traceback': False
    }

    try:
        body = iw.body.lower()
    except AttributeError:
        return tfacts

    tb_cond = [
        'traceback (most recent call last):' in body,
        'to see the full traceback' in body,
        re.search(RE_FILE_LINE, body),
    ]

    if any(tb_cond):
        tfacts['has_traceback'] = True

    return tfacts
