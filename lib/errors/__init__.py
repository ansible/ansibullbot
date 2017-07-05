#!/usr/bin/env python


# https://stackoverflow.com/a/1319675
class RateLimitError(Exception):
    """Used to trigger the ratelimiting decorator"""
