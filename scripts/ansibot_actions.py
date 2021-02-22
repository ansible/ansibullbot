#!/usr/bin/env python

import json

import requests

VALID_ACTIONS = frozenset((
    "assign",
    "cancel_ci",
    "cancel_ci_branch",
    "close",
    "close_migrated",
    "comments",
    "merge",
    "newlabel",
    "open",
    "rebuild",
    "rebuild_failed",
    "unassign",
    "uncomment",
    "unlabel"
))


def main():
    params = {
        "user": "ansible",
        "repo": "ansible",
    }

    resp = requests.get("http://localhost:5001/actions", params=params)
    if resp.status_code != 200:
        raise RuntimeException(resp.status_code)

    actions = json.loads(resp.content)

    print("<h1>Ansibot actions</h1>")
    for action_data in actions:
        gh_number = action_data.get("github_number")
        print(f"<h2><a href=\"https://github.com/ansible/ansible/issues/{gh_number}\">{gh_number}</a></h2")
        for action, value in sorted(action_data.items()):
            if action not in VALID_ACTIONS:
                continue

            if isinstance(value, bool):
                parsed_value = "yes" if value else "no"
            elif isinstance(value, list):
                parsed_value = ", ".join(value)
            else:
                raise AssertionError("value is of type %s" % type(value))

            print(f"{action}: {parsed_value}")


if __name__ == "__main__":
    main()
