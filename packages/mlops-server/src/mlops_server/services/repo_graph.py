from __future__ import annotations

MAX_BRANCHES = 20


def build_graph(github, repo: str, limit: int) -> dict:
    default = github.get_default_branch(repo)
    branches = github.list_branches(repo, MAX_BRANCHES)
    branches.sort(key=lambda b: (b.name != default, b.name))
    seen = {}
    for branch in branches:
        for commit in github.list_commits(repo, branch.name, limit):
            seen.setdefault(commit.sha, commit)
    ordered = sorted(seen.values(), key=lambda c: c.date, reverse=True)
    kept = ordered[: limit * 2]
    kept_shas = {c.sha for c in kept}
    for branch in branches:  # a branch head must never fall off the end
        if branch.sha in seen and branch.sha not in kept_shas:
            kept.append(seen[branch.sha])
            kept_shas.add(branch.sha)
    head = next((b.sha for b in branches if b.name == default), None)
    return {
        "repo": repo,
        "default_branch": default,
        "head": head,
        "branches": [
            {"name": b.name, "sha": b.sha, "default": b.name == default} for b in branches
        ],
        "commits": [
            {
                "sha": c.sha,
                "parents": list(c.parents),
                "message": c.message,
                "author": c.author,
                "date": c.date,
            }
            for c in kept
        ],
        "truncated": len(ordered) > len(kept),
    }
