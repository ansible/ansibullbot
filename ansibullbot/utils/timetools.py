import datetime
import logging


def strip_time_safely(tstring):
    """Try various formats to strip the time from a string"""
    res = None
    tsformats = (
        u'%Y-%m-%dT%H:%M:%SZ',
        u'%Y-%m-%dT%H:%M:%S.%f',
        u'%Y-%m-%dT%H:%M:%S',
        u'%Y-%m-%dT%H:%M:%S.%fZ',
        u'%a %b %d %H:%M:%S %Y',
        u'%Y-%m-%d',
    )
    for tsformat in tsformats:
        try:
            res = datetime.datetime.strptime(tstring, tsformat)
            break
        except ValueError as e:
            logging.debug(e)
    if res is None:
        logging.error(u'{} could not be stripped'.format(tstring))
        raise Exception(u'{} could not be stripped'.format(tstring))
    return res
