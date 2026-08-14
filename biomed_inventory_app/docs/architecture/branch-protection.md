# Branch Protection

Protect `main` in GitHub repository settings.

Required rules:

- Require pull request before merge.
- Require approval from CODEOWNERS.
- Require status checks before merge.
- Required status check: `CI / Python checks`.
- Require branches to be up to date before merge.
- Block force pushes.
- Block branch deletion.

This cannot be fully enforced by repository files alone; it must be enabled in GitHub settings or through the GitHub API.
