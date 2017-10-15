#!/usr/bin/env python

from unittest import TestCase
from ansibullbot.utils.timetools import strip_time_safely


class TestTimeStrip(TestCase):

    def test_strip_one(self):
        ts = '2017-06-01T17:54:00Z'
        to = strip_time_safely(ts)
        assert to.year == 2017
        assert to.month == 6
        assert to.day == 1

    def test_strip_two(self):
        ts = '2017-06-01T17:54:00.000'
        to = strip_time_safely(ts)
        assert to.year == 2017
        assert to.month == 6
        assert to.day == 1

    def test_strip_three(self):
        ts = '2017-06-01T17:54:00Z'
        to = strip_time_safely(ts)
        assert to.year == 2017
        assert to.month == 6
        assert to.day == 1

    def test_strip_four(self):
        ts = '2017-06-01T17:54:00ZDSFSDFDFSDFS'
        e = None
        try:
            to = strip_time_safely(ts)
        except Exception as e:
            pass
        assert e is not None
