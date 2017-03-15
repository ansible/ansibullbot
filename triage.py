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

from lib.triagers.ansible import AnsibleTriage


def main():
    description = "Triage issue and pullrequest queues for Ansible.\n"
    description += " (NOTE: only useful if you have commit access to"
    description += " the repo in question.)"

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument("--skip_no_update", action="store_true",
                        help="skip processing if updated_at hasn't changed")

    parser.add_argument("--skip_no_update_timeout", action="store_true",
                        help="ignore skip if last process is X days old")

    parser.add_argument("--collect_only", action="store_true",
                        help="stop after caching issues")

    parser.add_argument("--skip_module_repos", action="store_true",
                        help="ignore the module repos")
    parser.add_argument("--module_repos_only", action="store_true",
                        help="only process the module repos")

    parser.add_argument("--force_rate_limit", action="store_true",
                        help="debug: force the rate limit")

    parser.add_argument("--sort", default='desc', choices=['asc', 'desc'],
                        help="Direction to sort issues [desc=9-0 asc=0-9]")

    parser.add_argument("--logfile", type=str,
                        default='/var/log/ansibullbot.log',
                        help="Send logging to this file")
    parser.add_argument("--daemonize", action="store_true",
                        help="run in a continuos loop")
    parser.add_argument("--daemonize_interval", type=int, default=(30 * 60),
                        help="seconds to sleep between loop iterations")

    parser.add_argument("--skiprepo", action='append',
                        help="Github repo to skip triaging")

    parser.add_argument("--repo", "-r", type=str,
                        help="Github repo to triage (defaults to all)")

    parser.add_argument("--only_prs", action="store_true",
                        help="Triage pullrequests only")
    parser.add_argument("--only_issues", action="store_true",
                        help="Triage issues only")

    parser.add_argument("--only_open", action="store_true",
                        help="Triage open issues|prs only")
    parser.add_argument("--only_closed", action="store_true",
                        help="Triage closed issues|prs only")

    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Don't make any changes")
    parser.add_argument("--force", "-f", action="store_true",
                        help="Do not ask questions")
    parser.add_argument("--safe_force", action="store_true",
                        help="Prompt only on specific actions")
    parser.add_argument("--debug", "-d", action="store_true",
                        help="Debug output")
    parser.add_argument("--pause", "-p", action="store_true",
                        help="Always pause between prs|issues")

    parser.add_argument("--ignore_state", action="store_true",
                        help="Do not skip processing closed issues")

    parser.add_argument("--issue_component_matching", action="store_true",
                        help="Try to enumerate the component labels for issues")

    parser.add_argument(
        "--pr", "--id", type=str,
        help="Triage only the specified pr|issue (separated by commas)"
    )

    parser.add_argument("--start-at", "--resume_id", type=int,
                        help="Start triage at the specified pr|issue")
    parser.add_argument("--no_since", action="store_true",
                        help="Do not use the since keyword to fetch issues")
    args = parser.parse_args()

    # Run the triager ...
    AnsibleTriage(args).start()


if __name__ == "__main__":
    main()
