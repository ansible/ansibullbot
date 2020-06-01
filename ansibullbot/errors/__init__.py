class LabelWafflingError(Exception):
    """Label has been added/removed too many times"""


class RateLimitError(Exception):
    """Used to trigger the ratelimiting decorator"""


class ShippableNoData(Exception):
    """Shippable did not return data"""
