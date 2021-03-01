#!/usr/bin/env python

import requests
import yaml

from bson.json_util import loads


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


HTML_HEAD = \
"""
<!DOCTYPE html>
<html>
<head>
<style>
.div_heading {
    background-color: #CFC;
    padding: 10px;
    border: 1px solid green;
    margin: 5px;
}
.div_meta {
    background-color: #F0FFF0;
    padding: 2px;
    border: 1px solid green;
    margin: 5px;
    overflow: auto;
    max-height: 500px;
}
</style>
<script>
function showMeta(id) {
  var x = document.getElementById("meta"+id);
  if (x.style.display === "none") {
    x.style.display = "block";
  } else {
    x.style.display = "none";
  }
}
</script>
</head>
<body>
<h1>Ansibot actions</h1>
"""


def main():
    params = {
        "user": "ansible",
        "repo": "ansible",
    }

    resp = requests.get("http://127.0.0.1:5001/actions", params=params)
    if resp.status_code != 200:
        raise RuntimeError(resp.status_code)

    actions = loads(resp.content)

    page = HTML_HEAD.splitlines()
    for action_data in actions:
        gh_number = action_data.get("github_number")
        action_datetime = action_data.get("datetime")
        gh_title = action_data.get("meta", {}).get("title")
        gh_submitter = action_data.get("meta", {}).get("submitter")
        if action_datetime is not None:
            action_datetime = action_datetime.strftime("%a %d. %b %Y, %H:%M:%S.%f UTC")

        page.append(
            "<div class=\"div_heading\">"
            f"<a href=\"https://github.com/ansible/ansible/issues/{gh_number}\">#{gh_number}</a>"
            f" | {gh_title} by {gh_submitter} | {action_datetime}"
            "</div>"
        )

        valid_actions  = {action: value for action, value in sorted(action_data.items()) if action in VALID_ACTIONS}
        page.append("<pre>")
        page.append(yaml.dump(valid_actions))
        page.append("</pre>")

        action_id = str(action_data.get("_id"))
        action_meta = action_data.get("meta", {"meta": "N/A"})
        action_meta.pop('actions', None)
        page.append(f"<button onclick=\"showMeta('{action_id}')\">Show meta</button>")
        page.append(f"<div class=\"div_meta\" id=\"meta{action_id}\" style=\"display: none;\"><pre>")
        page.append(yaml.dump(action_meta))
        page.append("</pre>")
        page.append("</div>")

    page.append("</body>")
    page.append("</html>")

    return "\n".join(page)


if __name__ == "__main__":
    page = "Content-type: text/html\n\n"
    page += main()
    print(page)
