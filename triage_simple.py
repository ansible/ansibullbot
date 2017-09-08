#!/usr/bin/env python
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

import argparse
from ansibullbot.triagers.simpletriager import SimpleTriager


def main():
    description = "Triage issue and pullrequest queues for any github repo.\n"
    description += " (NOTE: only useful if you have commit access to"
    description += " the repo in question.)"

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("--configfile", type=str,
                        default='/tmp/triager_cache/config.cfg')
    parser.add_argument("--cachedir", type=str,
                        default='/tmp/triager_cache')
    parser.add_argument("--logfile", type=str,
                        default='/tmp/triager_cache/bot.log',
                        help="Send logging to this file")
    parser.add_argument("--daemonize", action="store_true",
                        help="run in a continuos loop")
    parser.add_argument("--daemonize_interval", type=int, default=(30 * 60),
                        help="seconds to sleep between loop iterations")

    parser.add_argument("--repo", "-r", type=str, required=True,
                        help="Github repo to triage")

    parser.add_argument("--debug", "-d", action="store_true",
                        help="Debug output")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")

    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Don't make any changes")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Do not ask questions")
    parser.add_argument("--always_pause", "-p", action="store_true",
                        help="Always pause between prs|issues")

    parser.add_argument(
        "--number", "--pr", "--id", type=str,
        help="Triage only the specified pr|issue (separated by commas)"
    )

    args = parser.parse_args()

    # Run the triager ...
    SimpleTriager(args).start()


if __name__ == "__main__":
    main()
