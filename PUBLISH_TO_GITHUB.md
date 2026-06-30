# Publish To GitHub

This repo is prepared for public publishing. It excludes Google credentials, tokens, uploaded files, drafts, packaged builds, and logs.

## Option 1: GitHub CLI

Install and sign in to GitHub CLI, then run:

```powershell
gh auth login
gh repo create calendar-assistant --public --source . --remote origin --push
```

## Option 2: GitHub Website

1. Create a new public repository on GitHub named `calendar-assistant`.
2. Copy the repository URL.
3. Run:

```powershell
git remote add origin https://github.com/YOUR-USERNAME/calendar-assistant.git
git push -u origin main
```

## Before Publishing

Confirm these files are not present:

- `credentials.json`
- `token.json`
- files in `uploads`
- files in `drafts`
- packaged `.zip` or `.exe` files
