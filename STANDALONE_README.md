# Calendar Assistant Standalone App

This package contains a Windows standalone build of Calendar Assistant.

## How to run

1. Open the `CalendarAssistant` folder.
2. Double-click `CalendarAssistant.exe`.
3. Keep the app window open while using Calendar Assistant.
4. The browser opens at `http://127.0.0.1:7871`.

## First-time Google setup

Use the Google Setup box in the browser to select your own OAuth desktop `credentials.json`.

The first Google Calendar search or save will open Google sign-in. After sign-in, the app stores `token.json` next to the `.exe` for that user's account.

## What not to share

Do not share these after using the app:

- `credentials.json`
- `token.json`
- files in `drafts`
- files in `uploads`

## OCR

Tesseract OCR is bundled in this package, so screenshots and images can be read without installing Tesseract separately. PDFs with selectable text also work.
