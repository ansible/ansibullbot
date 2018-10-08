#!/usr/bin/env python

import pytest

from unittest import TestCase
from ansibullbot.utils.timetools import strip_time_safely


class TestTimeStrip(TestCase):

    def test_strip_one(self):
        ts = u'2017-06-01T17:54:00Z'
        to = strip_time_safely(ts)
        assert to.year == 2017
        assert to.month == 6
        assert to.day == 1

    def test_strip_two(self):
        ts = u'2017-06-01T17:54:00.000'
        to = strip_time_safely(ts)
        assert to.year == 2017
        assert to.month == 6
        assert to.day == 1

    def test_strip_three(self):
        ts = u'2017-06-01T17:54:00Z'
        to = strip_time_safely(ts)
        assert to.year == 2017
        assert to.month == 6
        assert to.day == 1

    def test_strip_four(self):
        ts = u'2017-06-01T17:54:00ZDSFSDFDFSDFS'
        with pytest.raises(Exception):
            to = strip_time_safely(ts)
