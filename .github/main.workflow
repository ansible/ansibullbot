workflow "Main workflow" {
  resolves = ["WIP"]
  on = "pull_request"
}

action "WIP" {
  uses = "wip/action@v1.0.0"
  secrets = ["GITHUB_TOKEN"]
}
