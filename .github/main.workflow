workflow "Main workflow" {
  resolves = ["WIP"]
  on = "pull_request"
}

action "WIP" {
  uses = "wip/action@v1.0.0"
  secrets = ["GITHUB_TOKEN"]
}

workflow "On Push" {
  on = "push"
  resolves = ["Ansible Lint"]
}

action "Ansible Lint" {
  uses = "ansible/ansible-lint-action@master"
  env = {
    ACTION_PLAYBOOK_NAME = "playbooks/update-ansibullbot.yml"
  }
}
