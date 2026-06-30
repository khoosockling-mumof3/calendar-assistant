# Calendar Assistant

Calendar Assistant is a local Windows app for reviewing PDFs, screenshots, and images, extracting likely calendar events, checking Google Calendar for duplicates, and syncing reviewed events to Google Calendar.

The app runs locally on the user's computer. It does not include the author's Google credentials or personal tokens.

## Download The Standalone App

Most users should download the standalone release ZIP from this repository's Releases page.

The standalone ZIP includes:

- `CalendarAssistant.exe`
- the browser-based review app
- the Python runtime bundled by PyInstaller
- Tesseract OCR for screenshots and images
- PDF/image parsing dependencies

Users do **not** need to install Python, PyInstaller, or Tesseract.

After downloading:

1. Extract the ZIP.
2. Open the `CalendarAssistant` folder.
3. Double-click `CalendarAssistant.exe`.
4. Use the Google Setup box to provide your own OAuth desktop `credentials.json`.
5. Sign in to Google when prompted.

## Google Calendar Setup

Each user must provide their own Google OAuth desktop credentials. The app stores that file locally as `credentials.json` beside the app, then creates a local `token.json` after Google sign-in.

Do not share:

- `credentials.json`
- `token.json`
- files in `uploads`
- files in `drafts`

Google Calendar scope used:

`https://www.googleapis.com/auth/calendar.events`

## Features

- Upload PDFs, screenshots, and images.
- Extract likely event title, date, start time, end time, location, description, and event type.
- Split multi-event tables into separate review cards.
- Search Google Calendar for similar events in a chosen date range.
- Choose per event whether to update an existing event, create a new event, or skip.
- Save reviewed drafts as JSON.
- Sync selected events to Google Calendar after clicking `Save Edited Draft`.

## Run From Source

Developers can run from source if they prefer.

Requirements:

- Windows
- Python 3.12 or newer
- Tesseract OCR if running from source and using screenshot/image OCR

Steps:

1. Clone or download this repository.
2. Double-click `Install Dependencies.bat`.
3. Double-click `Start Calendar Assistant.bat`.
4. In the browser, use the Google Setup box to select your own OAuth desktop `credentials.json`.

PDFs with selectable text work without Tesseract. Screenshots and images require Tesseract when running from source.

## Building A Standalone Windows App

This is only needed for developers who want to rebuild the release package.

```powershell
python -m pip install pyinstaller -r requirements.txt
pyinstaller --noconfirm --clean --name CalendarAssistant --add-data "index.html;." --add-data "assets;assets" app.py
```

To bundle OCR, place a `Tesseract-OCR` folder beside `CalendarAssistant.exe` containing `tesseract.exe`, required DLLs, and `tessdata/eng.traineddata`.
