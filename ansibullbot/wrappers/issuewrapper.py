#!/usr/bin/python
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible. If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function

import six

from .defaultwrapper import DefaultWrapper


@six.python_2_unicode_compatible
class IssueWrapper(DefaultWrapper):

    REQUIRED_SECTIONS = [
        u'issue type',
        u'component name',
        u'ansible version',
        u'summary'
    ]

    def noop(self):
        pass

    def __str__(self):
        return self.instance.html_url
