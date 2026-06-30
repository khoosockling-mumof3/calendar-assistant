# Calendar Assistant

Calendar Assistant is a local Windows app for reviewing PDFs, screenshots, and images, extracting likely calendar events, checking Google Calendar for duplicates, and saving reviewed events to Google Calendar.

The app runs locally on the user's computer. It does not include any Google credentials or tokens.

## Features

- Upload PDFs, screenshots, and images.
- Extract likely event title, date, start time, end time, location, description, and event type.
- Split multi-event tables into separate review cards.
- Search Google Calendar for similar events in a chosen date range.
- Choose per event whether to update an existing event, create a new event, or skip.
- Save reviewed drafts as JSON.
- Sync selected events to Google Calendar after clicking `Save Edited Draft`.

## Privacy and credentials

This repository intentionally does not include:

- `credentials.json`
- `token.json`
- uploaded files
- saved drafts
- personal logs
- packaged build artifacts

Each user must provide their own Google OAuth desktop credentials in the in-app Google Setup box. After sign-in, the app creates a local `token.json` for that user. Do not commit or share `credentials.json` or `token.json`.

Google Calendar scope used:

`https://www.googleapis.com/auth/calendar.events`

## Run From Source

Requirements:

- Windows
- Python 3.12 or newer
- Tesseract OCR for screenshot/image OCR

Steps:

1. Clone or download this repository.
2. Double-click `Install Dependencies.bat`.
3. Double-click `Start Calendar Assistant.bat`.
4. In the browser, use the Google Setup box to select your own OAuth desktop `credentials.json`.
5. Upload files and review the extracted events.

PDFs with selectable text work without Tesseract. Screenshots and images require Tesseract.

## Building A Standalone Windows App

Install PyInstaller, then build with:

```powershell
python -m pip install pyinstaller -r requirements.txt
pyinstaller --noconfirm --clean --name CalendarAssistant --add-data "index.html;." --add-data "assets;assets" app.py
```

The output is created in `dist/CalendarAssistant`.

If you want OCR to work without requiring users to install Tesseract, place a `Tesseract-OCR` folder beside `CalendarAssistant.exe` containing `tesseract.exe`, required DLLs, and `tessdata/eng.traineddata`.
