# Calendar Assistant Shareable Package

This folder contains the Calendar Assistant app code without any personal Google credentials, tokens, uploaded files, or drafts.

## Before sharing

Do not add these files to the package:

- `credentials.json`
- `token.json`
- anything in `drafts`
- anything in `uploads`

## How another user runs it

1. Install Python 3.12 or newer.
2. Double-click `Install Dependencies.bat`.
3. Install Tesseract OCR if they want screenshot/image OCR.
4. Double-click `Start Calendar Assistant.bat`.
5. In the browser, use the Google Setup box to choose their own OAuth desktop `credentials.json`.
6. The first Google Calendar search or save will open Google sign-in.

## Google OAuth

Each user should use their own Google OAuth desktop credentials. The app saves those credentials locally as `credentials.json` and saves the user sign-in token locally as `token.json`.

The app uses this scope:

`https://www.googleapis.com/auth/calendar.events`

## Packaging note

This is a portable source package, not a single-file executable. To make it a true standalone Windows app, build it with a tool such as PyInstaller on a machine where packaging tools are installed.
