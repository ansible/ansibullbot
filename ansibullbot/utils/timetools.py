import datetime
import logging

from ansibullbot._text_compat import to_text


def strip_time_safely(tstring):
    """Try various formats to strip the time from a string"""
    tsformats = (
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%fZ',
        '%a %b %d %H:%M:%S %Y',
        '%Y-%m-%d',
    )

    for tsformat in tsformats:
        try:
            return datetime.datetime.strptime(tstring, tsformat)
        except ValueError as e:
            text_e = to_text(e)
            if 'unconverted data remains' in text_e and tstring.endswith('Z'):
                # '2020-11-10T07:39:58.6833333Z'
                new_tstring = tstring[:-len(text_e.split(':')[-1].strip())]+'Z'
                try:
                    return datetime.datetime.strptime(new_tstring, '%Y-%m-%dT%H:%M:%S.%fZ')
                except ValueError:
                    pass

    logging.error(f'{tstring} could not be stripped')
    raise Exception(f'{tstring} could not be stripped')
