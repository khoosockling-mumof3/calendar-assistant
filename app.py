import cgi
import base64
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib import error as urlerror
from urllib import request as urlrequest
import webbrowser

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from dateutil import parser as date_parser
except Exception:
    date_parser = None


RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
USER_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
APP_DIR = RESOURCE_DIR
UPLOAD_DIR = USER_DIR / "uploads"
DRAFT_DIR = USER_DIR / "drafts"
ASSET_DIR = RESOURCE_DIR / "assets"
CREDENTIALS_PATH = USER_DIR / "credentials.json"
TOKEN_PATH = USER_DIR / "token.json"
GOOGLE_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
PORT = int(os.environ.get("CALENDAR_ASSISTANT_PORT", "7871"))

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
PDF_EXTENSIONS = {".pdf"}

TIME_PATTERN = re.compile(
    r"\b(?:(?P<hour>\d{1,2})(?P<sep>[:.])(?P<minute>\d{2})|(?P<compact>\d{3,4})|(?P<hour_only>\d{1,2}))\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?|am|pm)?\b",
    re.IGNORECASE,
)
DATE_PATTERNS = [
    re.compile(
        r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d{1,2}(?:st|nd|rd|th)?\s*"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?(?:,?\s+\d{4})?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
    re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b"),
]
WEEKDAY_PATTERN = re.compile(r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\b", re.IGNORECASE)
EVENT_WORDS = re.compile(
    r"\b(?:holiday|closure|closed|training|event|meeting|appointment|practice|club|concert|class|camp|"
    r"orientation|conference|cancelled|canceled|rescheduled|postponed)\b",
    re.IGNORECASE,
)


def ensure_dirs():
    UPLOAD_DIR.mkdir(exist_ok=True)
    DRAFT_DIR.mkdir(exist_ok=True)


def safe_filename(name):
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", Path(name).name).strip(" .")
    return cleaned or "uploaded-file"


def normalize_spaces(value):
    return re.sub(r"\s+", " ", value or "").strip()


def read_pdf_text(path):
    parts = []
    if pdfplumber:
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    parts.append(page.extract_text() or "")
        except Exception:
            parts = []
    if not any(part.strip() for part in parts) and PdfReader:
        try:
            reader = PdfReader(str(path))
            parts = [(page.extract_text() or "") for page in reader.pages]
        except Exception:
            parts = []
    return "\n".join(parts).strip()


def find_tesseract():
    common_paths = [
        USER_DIR / "Tesseract-OCR" / "tesseract.exe",
        RESOURCE_DIR / "Tesseract-OCR" / "tesseract.exe",
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ]
    for candidate in common_paths:
        if candidate.exists():
            return str(candidate)
    found = shutil.which("tesseract")
    if found:
        return found
    return ""


def read_image_text(path):
    tesseract = find_tesseract()
    if not tesseract:
        return "", "Image OCR is not available on this computer yet. The draft was created for manual review."
    env = os.environ.copy()
    tessdata = Path(tesseract).resolve().parent / "tessdata"
    if tessdata.exists():
        env["TESSDATA_PREFIX"] = str(tessdata)
    try:
        result = subprocess.run(
            [tesseract, str(path), "stdout", "-l", "eng"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            env=env,
        )
    except Exception as exc:
        return "", f"Image OCR could not run: {exc}"
    if result.returncode != 0:
        return "", normalize_spaces(result.stderr) or "Image OCR did not return readable text."
    return result.stdout.strip(), ""


def classify_change_type(text):
    lower = text.lower()
    cancellation = ["cancelled", "canceled", "cancel", "no longer taking place", "called off"]
    reschedule = ["rescheduled", "reschedule", "new time", "moved to", "postponed", "changed to"]
    if any(word in lower for word in cancellation):
        return "cancellation"
    if any(word in lower for word in reschedule):
        return "reschedule"
    return "new event"


def extract_date(text):
    for pattern in DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            return normalize_spaces(match.group(0))
    return ""


def extract_context_year(text):
    match = re.search(r"\b(20\d{2}|19\d{2})\b", text or "")
    return match.group(1) if match else ""


def date_has_year(value):
    return bool(re.search(r"\b(20\d{2}|19\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", value or ""))


def has_date(text):
    return bool(extract_date(text))


def clean_time_match(match):
    ampm = (match.group("ampm") or "").replace(".", "").lower()
    compact = match.group("compact")
    if compact:
        if not ampm:
            return ""
        hour = compact[:-2]
        minute = compact[-2:]
        return f"{int(hour)}:{minute} {ampm}".strip()
    hour = match.group("hour") or match.group("hour_only")
    minute = match.group("minute") or ""
    if match.group("hour_only") and not ampm:
        return ""
    ampm = (match.group("ampm") or "").replace(".", "").lower()
    if minute:
        value = f"{hour}:{minute}"
    else:
        value = hour
    return f"{value} {ampm}".strip()


def extract_times(text):
    ranges = re.finditer(
        r"(?P<first>(?:\d{1,2}[:.]\d{2}|\d{3,4}|\d{1,2})\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?)\s*"
        r"(?:-|to|until|through)\s*"
        r"(?P<second>(?:\d{1,2}[:.]\d{2}|\d{3,4}|\d{1,2})\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?)",
        text,
        re.IGNORECASE,
    )
    for match in ranges:
        first = parse_single_time(match.group("first"))
        second = parse_single_time(match.group("second"))
        if first or second:
            return first, second

    values = []
    for match in TIME_PATTERN.finditer(text):
        value = clean_time_match(match)
        if value and value not in values:
            values.append(value)
    return (values[0] if values else "", values[1] if len(values) > 1 else "")


def parse_single_time(value):
    match = TIME_PATTERN.search(value or "")
    return clean_time_match(match) if match else ""


def extract_location(text):
    lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
    location_markers = ("location", "where", "venue", "place", "address", "room")
    for line in lines:
        lower = line.lower()
        for marker in location_markers:
            if lower.startswith(marker):
                return normalize_spaces(re.sub(r"^[^:,-]+[:,-]\s*", "", line))
    for line in lines:
        lower = line.lower()
        if any(token in lower for token in [" room ", " hall", " gym", " center", " centre", " field", " park", " library"]):
            return line
    return ""


def title_from_row(text):
    line = normalize_spaces(text.replace("_|", " ").replace("|", " ").replace("_", " "))
    has_gazetted_public_holiday = bool(re.search(r"\bGazetted\s+Public\s+Holiday\b", line, re.IGNORECASE))
    line = re.sub(r"\bTerm\s+\d+\b", " ", line, flags=re.IGNORECASE)
    for pattern in DATE_PATTERNS:
        line = pattern.sub(" ", line, count=1)
    line = WEEKDAY_PATTERN.sub(" ", line, count=1)
    line = re.sub(r"\bGazetted\s+Public\s+Holiday\b", " ", line, flags=re.IGNORECASE)
    line = re.sub(r"\bPublic\s+Holiday\s+\d{4}\b", " ", line, flags=re.IGNORECASE)
    line = re.sub(r"\bSchool\s+Date\s+Day\s+Event\s+Remarks\b", " ", line, flags=re.IGNORECASE)
    line = normalize_spaces(line.strip(" :-*,?"))
    if not line and has_gazetted_public_holiday:
        return "Public Holiday"
    return line[:120]


def extract_title(text, filename):
    lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
    ignored = ("date", "time", "location", "where", "venue", "description", "when")
    if len(lines) == 1 and has_date(lines[0]):
        row_title = title_from_row(lines[0])
        if row_title:
            return row_title
    for line in lines[:8]:
        lower = line.lower().strip(":")
        if len(line) >= 3 and not any(lower.startswith(word) for word in ignored):
            return line[:120]
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip().title()


def summarize_description(text):
    lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
    return "\n".join(lines[:12])[:1200]


def split_event_chunks(text):
    lines = [normalize_spaces(line) for line in text.splitlines() if normalize_spaces(line)]
    if not lines:
        return []

    row_chunks = []
    for line in lines:
        lower = line.lower()
        if "date" in lower and "event" in lower and "remarks" in lower:
            continue
        if has_date(line) and (EVENT_WORDS.search(line) or WEEKDAY_PATTERN.search(line) or extract_times(line)[0]):
            row_chunks.append(line)
    if len(row_chunks) > 1:
        return row_chunks

    paragraph_chunks = [normalize_spaces(chunk) for chunk in re.split(r"\n\s*\n+", text) if normalize_spaces(chunk)]
    event_like = [chunk for chunk in paragraph_chunks if has_date(chunk) or extract_times(chunk)[0] or EVENT_WORDS.search(chunk)]
    if len(event_like) > 1:
        return event_like

    date_line_indexes = [idx for idx, line in enumerate(lines) if has_date(line)]
    if len(date_line_indexes) > 1:
        chunks = []
        for pos, start in enumerate(date_line_indexes):
            end = date_line_indexes[pos + 1] if pos + 1 < len(date_line_indexes) else min(len(lines), start + 5)
            chunk = "\n".join(lines[start:end])
            if EVENT_WORDS.search(chunk) or extract_times(chunk)[0] or len(chunk) < 220:
                chunks.append(chunk)
        if len(chunks) > 1:
            return chunks

    return [text]


def build_event(filename, text, note="", sequence=None, context_year=""):
    start_time, end_time = extract_times(text)
    date_value = extract_date(text)
    if date_value and context_year and not date_has_year(date_value):
        date_value = f"{date_value} {context_year}"
    event = {
        "title": extract_title(text, filename),
        "date": date_value,
        "start_time": start_time,
        "end_time": end_time,
        "location": extract_location(text),
        "description": summarize_description(text),
        "change_type": classify_change_type(text),
        "source_file": filename,
        "google_calendar_id": "primary",
        "google_event_id": "",
        "google_duplicate_action": "create_new",
        "google_duplicate_match_id": "",
        "google_duplicate_match": {},
        "google_duplicate_matches": [],
        "google_sync_status": "not synced",
        "confidence": "needs review",
        "notes": note,
    }
    if sequence is not None:
        event["source_event_number"] = sequence
    filled = sum(1 for key in ["title", "date", "start_time", "location"] if event.get(key))
    if filled >= 4 and text:
        event["confidence"] = "medium"
    elif filled >= 2 and text:
        event["confidence"] = "low"
    return event


def process_file(path, original_name):
    ext = path.suffix.lower()
    note = ""
    if ext in PDF_EXTENSIONS:
        text = read_pdf_text(path)
        if not text:
            note = "No selectable PDF text was found. If this is a scanned PDF, review the fields manually."
    elif ext in IMAGE_EXTENSIONS:
        text, note = read_image_text(path)
    else:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        note = "This file type is not a PDF or image, so extraction may be limited."
    chunks = split_event_chunks(text)
    if len(chunks) > 1:
        split_note = f"{len(chunks)} possible events were found in this file. Please review each one."
        note = f"{note} {split_note}".strip()
    context_year = extract_context_year(text)
    return [build_event(original_name, chunk, note, idx + 1, context_year) for idx, chunk in enumerate(chunks)]


def parse_event_datetime(event):
    if not date_parser:
        raise ValueError("Date parsing is not available in this Python environment.")
    date_text = normalize_spaces(event.get("date", ""))
    if not date_text:
        raise ValueError("Missing date.")
    default = dt.datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)
    parsed_date = date_parser.parse(date_text, fuzzy=True, default=default)
    start_time = normalize_spaces(event.get("start_time", ""))
    end_time = normalize_spaces(event.get("end_time", ""))
    timezone = dt.datetime.now().astimezone().tzinfo

    if start_time:
        start = date_parser.parse(f"{parsed_date.date()} {start_time}", fuzzy=True)
        if end_time:
            end = date_parser.parse(f"{parsed_date.date()} {end_time}", fuzzy=True)
        else:
            end = start + dt.timedelta(hours=1)
        if end <= start:
            end = end + dt.timedelta(days=1)
        start = start.replace(tzinfo=timezone)
        end = end.replace(tzinfo=timezone)
        return {
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }

    start_day = parsed_date.date()
    return {
        "start": {"date": start_day.isoformat()},
        "end": {"date": (start_day + dt.timedelta(days=1)).isoformat()},
    }


def parse_event_start_for_compare(event):
    when = parse_event_datetime(event)
    start = when["start"]
    if "dateTime" in start:
        return dt.datetime.fromisoformat(start["dateTime"])
    return dt.datetime.fromisoformat(f"{start['date']}T00:00:00").replace(tzinfo=dt.datetime.now().astimezone().tzinfo)


def event_to_google_body(event):
    when = parse_event_datetime(event)
    body = {
        "summary": normalize_spaces(event.get("title", "")) or "Untitled event",
        "location": normalize_spaces(event.get("location", "")),
        "description": normalize_spaces(event.get("description", "")),
        **when,
    }
    return {key: value for key, value in body.items() if value}


def google_event_start_for_compare(item):
    start = item.get("start", {})
    value = start.get("dateTime") or start.get("date")
    if not value:
        return None
    if "T" in value:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.datetime.fromisoformat(f"{value}T00:00:00").replace(tzinfo=dt.datetime.now().astimezone().tzinfo)


def normalize_similarity_text(value):
    return re.sub(r"[^a-z0-9 ]+", " ", (value or "").lower())


def token_set(value):
    return {token for token in normalize_similarity_text(value).split() if len(token) > 1}


def jaccard_similarity(left, right):
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def event_similarity_score(draft, google_event):
    score = 0
    reasons = []
    title_score = jaccard_similarity(draft.get("title", ""), google_event.get("summary", ""))
    if title_score >= 0.65:
        score += 4
        reasons.append("similar title")
    elif title_score >= 0.35:
        score += 2
        reasons.append("partly similar title")

    try:
        draft_start = parse_event_start_for_compare(draft)
    except Exception:
        draft_start = None
    google_start = google_event_start_for_compare(google_event)
    if draft_start and google_start:
        minutes = abs((draft_start - google_start).total_seconds()) / 60
        if draft_start.date() == google_start.date():
            score += 3
            reasons.append("same date")
        if minutes <= 30:
            score += 3
            reasons.append("similar time")
        elif minutes <= 120:
            score += 1
            reasons.append("nearby time")

    location_score = jaccard_similarity(draft.get("location", ""), google_event.get("location", ""))
    if location_score >= 0.6:
        score += 2
        reasons.append("similar location")
    elif draft.get("location") and google_event.get("location") and location_score > 0:
        score += 1
        reasons.append("partly similar location")

    return score, reasons


def fetch_google_events(calendar_id, start_date, end_date):
    access_token = get_access_token()
    encoded_calendar = quote(calendar_id or "primary", safe="")
    time_min = f"{start_date}T00:00:00Z"
    time_max = f"{end_date}T23:59:59Z"
    params = urlencode({
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "2500",
    })
    url = f"https://www.googleapis.com/calendar/v3/calendars/{encoded_calendar}/events?{params}"
    response = http_json(url, headers={"Authorization": f"Bearer {access_token}"})
    return response.get("items", [])


def format_google_event_match(item, score, reasons):
    start = item.get("start", {})
    end = item.get("end", {})
    return {
        "id": item.get("id", ""),
        "title": item.get("summary", "(untitled)"),
        "start": start.get("dateTime") or start.get("date") or "",
        "end": end.get("dateTime") or end.get("date") or "",
        "location": item.get("location", ""),
        "html_link": item.get("htmlLink", ""),
        "score": score,
        "reasons": reasons,
    }


def find_duplicate_matches(events, start_date, end_date):
    by_calendar = {}
    for event in events:
        calendar_id = normalize_spaces(event.get("google_calendar_id", "")) or "primary"
        by_calendar.setdefault(calendar_id, []).append(event)

    results = []
    for calendar_id, draft_events in by_calendar.items():
        google_events = fetch_google_events(calendar_id, start_date, end_date)
        for index, draft in enumerate(events):
            if (normalize_spaces(draft.get("google_calendar_id", "")) or "primary") != calendar_id:
                continue
            matches = []
            for item in google_events:
                if item.get("status") == "cancelled":
                    continue
                score, reasons = event_similarity_score(draft, item)
                if score >= 6:
                    matches.append(format_google_event_match(item, score, reasons))
            matches.sort(key=lambda match: match["score"], reverse=True)
            results.append({"index": index, "matches": matches[:5]})
    return results


def load_google_client_config():
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(f"Missing OAuth desktop credentials: {CREDENTIALS_PATH}")
    data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
    config = data.get("installed") or data.get("web")
    if not config:
        raise ValueError("credentials.json must contain OAuth desktop credentials.")
    return config


def validate_google_credentials_text(text):
    data = json.loads(text)
    config = data.get("installed") or data.get("web")
    if not config:
        raise ValueError("The file must be a Google OAuth desktop credentials JSON file.")
    required = ["client_id", "auth_uri", "token_uri"]
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise ValueError(f"credentials.json is missing: {', '.join(missing)}")
    return data


def google_setup_status():
    client_id = ""
    credential_type = ""
    if CREDENTIALS_PATH.exists():
        try:
            data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
            config = data.get("installed") or data.get("web") or {}
            client_id = config.get("client_id", "")
            credential_type = "desktop" if data.get("installed") else "web"
        except Exception:
            credential_type = "invalid"
    return {
        "credentials_configured": CREDENTIALS_PATH.exists(),
        "token_exists": TOKEN_PATH.exists(),
        "client_id_hint": client_id[:12] + "..." if client_id else "",
        "credential_type": credential_type,
        "scope": GOOGLE_CALENDAR_SCOPE,
    }


def token_is_valid(token):
    return bool(token.get("access_token")) and token.get("expires_at", 0) > time.time() + 60


def http_json(url, method="GET", payload=None, headers=None):
    data = None
    request_headers = headers or {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **request_headers}
    req = urlrequest.Request(url, data=data, method=method, headers=request_headers)
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
            return json.loads(text) if text else {}
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google Calendar API error {exc.code}: {detail}") from exc


def token_request(config, form):
    data = urlencode(form).encode("utf-8")
    req = urlrequest.Request(
        config["token_uri"],
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlrequest.urlopen(req, timeout=30) as response:
            token = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OAuth token error {exc.code}: {detail}") from exc
    token["expires_at"] = time.time() + int(token.get("expires_in", 3600))
    existing = load_token()
    if existing.get("refresh_token") and not token.get("refresh_token"):
        token["refresh_token"] = existing["refresh_token"]
    TOKEN_PATH.write_text(json.dumps(token, indent=2), encoding="utf-8")
    return token


def load_token():
    if not TOKEN_PATH.exists():
        return {}
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def refresh_access_token(config, token):
    if not token.get("refresh_token"):
        return {}
    return token_request(config, {
        "client_id": config["client_id"],
        "client_secret": config.get("client_secret", ""),
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    })


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    code = ""
    error = ""

    def log_message(self, format, *args):
        return

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        OAuthCallbackHandler.code = params.get("code", [""])[0]
        OAuthCallbackHandler.error = params.get("error", [""])[0]
        message = "Authorization received. You can close this browser tab and return to Calendar Assistant."
        data = message.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_oauth_flow(config):
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    OAuthCallbackHandler.code = ""
    OAuthCallbackHandler.error = ""
    callback_server = ThreadingHTTPServer(("127.0.0.1", 0), OAuthCallbackHandler)
    port = callback_server.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/oauth2callback"
    auth_url = f"{config['auth_uri']}?{urlencode({
        'client_id': config['client_id'],
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': GOOGLE_CALENDAR_SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    })}"

    print("\nGoogle authorization is needed.")
    print("A browser window will open. Sign in and allow Calendar event access.")
    webbrowser.open(auth_url)
    thread = threading.Thread(target=callback_server.handle_request, daemon=True)
    thread.start()
    thread.join(timeout=180)
    callback_server.server_close()
    if OAuthCallbackHandler.error:
        raise RuntimeError(f"Google authorization failed: {OAuthCallbackHandler.error}")
    if not OAuthCallbackHandler.code:
        raise RuntimeError("Google authorization timed out before a code was received.")
    return token_request(config, {
        "client_id": config["client_id"],
        "client_secret": config.get("client_secret", ""),
        "code": OAuthCallbackHandler.code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    })


def get_access_token():
    config = load_google_client_config()
    token = load_token()
    if token_is_valid(token):
        return token["access_token"]
    if token.get("refresh_token"):
        refreshed = refresh_access_token(config, token)
        if token_is_valid(refreshed):
            return refreshed["access_token"]
    return run_oauth_flow(config)["access_token"]


def sync_events_to_google_calendar(events):
    print_sync_summary(events)
    access_token = get_access_token()
    results = []
    for event in events:
        calendar_id = normalize_spaces(event.get("google_calendar_id", "")) or "primary"
        duplicate_action = normalize_spaces(event.get("google_duplicate_action", "")) or "create_new"
        if duplicate_action == "skip":
            event["google_sync_status"] = "skipped by duplicate review"
            results.append({"title": event.get("title"), "status": event["google_sync_status"]})
            continue
        if duplicate_action == "update_existing":
            match = event.get("google_duplicate_match") if isinstance(event.get("google_duplicate_match"), dict) else {}
            match_id = normalize_spaces(event.get("google_duplicate_match_id", ""))
            for candidate in event.get("google_duplicate_matches", []):
                if isinstance(candidate, dict) and candidate.get("id") == match_id:
                    match = candidate
                    event["google_duplicate_match"] = candidate
                    break
            if match.get("id"):
                event["google_event_id"] = match["id"]
        event_id = normalize_spaces(event.get("google_event_id", ""))
        if event.get("change_type") == "cancellation" and not event_id:
            event["google_sync_status"] = "skipped cancellation without google_event_id"
            results.append({"title": event.get("title"), "status": event["google_sync_status"]})
            continue
        body = event_to_google_body(event)
        if event.get("change_type") == "cancellation" and event_id:
            body["status"] = "cancelled"
        encoded_calendar = quote(calendar_id, safe="")
        headers = {"Authorization": f"Bearer {access_token}"}
        if event_id:
            encoded_event = quote(event_id, safe="")
            url = f"https://www.googleapis.com/calendar/v3/calendars/{encoded_calendar}/events/{encoded_event}"
            response = http_json(url, method="PATCH", payload=body, headers=headers)
            event["google_sync_status"] = "updated"
        else:
            url = f"https://www.googleapis.com/calendar/v3/calendars/{encoded_calendar}/events"
            response = http_json(url, method="POST", payload=body, headers=headers)
            event["google_event_id"] = response.get("id", "")
            event["google_sync_status"] = "created"
        results.append({
            "title": event.get("title"),
            "status": event.get("google_sync_status"),
            "google_event_id": event.get("google_event_id"),
            "html_link": response.get("htmlLink", ""),
        })
    latest = next(
        (
            item for item in reversed(results)
            if item.get("status") in {"created", "updated"} and item.get("html_link")
        ),
        {},
    )
    print(f"Google Calendar sync complete: {len(results)} result(s).")
    if latest.get("html_link"):
        webbrowser.open(latest["html_link"])
    return {
        "synced": True,
        "message": "Google Calendar sync complete.",
        "results": results,
        "latest_event_link": latest.get("html_link", ""),
        "latest_event_title": latest.get("title", ""),
    }


def print_sync_summary(events):
    print("\nSyncing saved draft to Google Calendar")
    print("=" * 48)
    for index, event in enumerate(events, 1):
        duplicate_action = normalize_spaces(event.get("google_duplicate_action", "")) or "create_new"
        action = "update" if normalize_spaces(event.get("google_event_id", "")) else "create"
        if duplicate_action == "skip":
            action = "skip"
        elif duplicate_action == "create_new":
            action = "create"
        elif duplicate_action == "update_existing":
            action = "update"
        if event.get("change_type") == "cancellation" and not event.get("google_event_id"):
            action = "skip cancellation without Google event ID"
        print(f"{index}. {action.upper()}: {event.get('title') or 'Untitled event'}")
        print(f"   Date: {event.get('date') or '(missing)'}")
        print(f"   Time: {event.get('start_time') or '(all day)'}{(' to ' + event.get('end_time')) if event.get('end_time') else ''}")
        print(f"   Location: {event.get('location') or '(none)'}")
        print(f"   Calendar: {event.get('google_calendar_id') or 'primary'}")
    print("=" * 48)


def save_draft(events):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    draft_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    payload = {
        "draft_id": draft_id,
        "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        "calendar_connected": False,
        "events": events,
    }
    path = DRAFT_DIR / f"{draft_id}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, payload


def json_response(handler, status, payload):
    data = json.dumps(payload, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


class CalendarAssistantHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            return self.serve_file(APP_DIR / "index.html", "text/html; charset=utf-8")
        if path.startswith("/assets/"):
            target = (APP_DIR / path.lstrip("/")).resolve()
            if APP_DIR in target.parents and target.exists():
                content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
                return self.serve_file(target, content_type)
        if path == "/api/drafts":
            drafts = []
            for draft in sorted(DRAFT_DIR.glob("*.json"), reverse=True):
                try:
                    data = json.loads(draft.read_text(encoding="utf-8"))
                    drafts.append({
                        "name": draft.name,
                        "path": str(draft),
                        "created_at": data.get("created_at", ""),
                        "event_count": len(data.get("events", [])),
                    })
                except Exception:
                    continue
            return json_response(self, 200, {"drafts": drafts})
        if path == "/api/setup-status":
            return json_response(self, 200, google_setup_status())
        return json_response(self, 404, {"error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/upload":
            return self.handle_upload()
        if path == "/api/save-draft":
            return self.handle_save_draft()
        if path == "/api/search-duplicates":
            return self.handle_search_duplicates()
        if path == "/api/setup-credentials":
            return self.handle_setup_credentials()
        if path == "/api/sign-out-google":
            return self.handle_sign_out_google()
        return json_response(self, 404, {"error": "Not found"})

    def serve_file(self, path, content_type):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_upload(self):
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
        })
        fields = form["files"] if "files" in form else []
        if not isinstance(fields, list):
            fields = [fields]
        events = []
        for item in fields:
            if not getattr(item, "filename", ""):
                continue
            original = safe_filename(item.filename)
            saved_name = f"{uuid.uuid4().hex[:8]}-{original}"
            saved_path = UPLOAD_DIR / saved_name
            with saved_path.open("wb") as handle:
                shutil.copyfileobj(item.file, handle)
            events.extend(process_file(saved_path, original))
        if not events:
            return json_response(self, 400, {"error": "Choose at least one PDF, screenshot, or image."})
        draft_path, payload = save_draft(events)
        payload["draft_path"] = str(draft_path)
        return json_response(self, 200, payload)

    def handle_save_draft(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return json_response(self, 400, {"error": "The draft could not be read."})
        events = payload.get("events", [])
        if not isinstance(events, list):
            return json_response(self, 400, {"error": "Draft events must be a list."})
        draft_path, saved = save_draft(events)
        saved["draft_path"] = str(draft_path)
        try:
            sync_result = sync_events_to_google_calendar(events)
            saved["calendar_connected"] = bool(sync_result.get("synced"))
            saved["google_calendar_sync"] = sync_result
            saved["events"] = events
            draft_path.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            saved["calendar_connected"] = False
            saved["google_calendar_sync"] = {
                "synced": False,
                "message": f"Google Calendar sync failed: {exc}",
                "results": [],
            }
            saved["events"] = events
            draft_path.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
            return json_response(self, 500, saved)
        return json_response(self, 200, saved)

    def handle_search_duplicates(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception:
            return json_response(self, 400, {"error": "The duplicate search request could not be read."})
        events = payload.get("events", [])
        start_date = normalize_spaces(payload.get("start_date", ""))
        end_date = normalize_spaces(payload.get("end_date", ""))
        if not isinstance(events, list):
            return json_response(self, 400, {"error": "Draft events must be a list."})
        if not start_date or not end_date:
            return json_response(self, 400, {"error": "Choose both a start date and an end date."})
        try:
            matches = find_duplicate_matches(events, start_date, end_date)
        except Exception as exc:
            return json_response(self, 500, {"error": f"Duplicate search failed: {exc}"})
        return json_response(self, 200, {"matches": matches})

    def handle_setup_credentials(self):
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
        })
        if "credentials" not in form or not getattr(form["credentials"], "file", None):
            return json_response(self, 400, {"error": "Choose a Google OAuth credentials JSON file."})
        item = form["credentials"]
        try:
            raw = item.file.read()
            text = raw.decode("utf-8")
            data = validate_google_credentials_text(text)
        except Exception as exc:
            return json_response(self, 400, {"error": f"Credentials file could not be used: {exc}"})
        CREDENTIALS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if TOKEN_PATH.exists():
            try:
                TOKEN_PATH.unlink()
            except Exception:
                pass
        return json_response(self, 200, {
            "message": "Google credentials saved. Sign in will open the first time Google Calendar is used.",
            **google_setup_status(),
        })

    def handle_sign_out_google(self):
        removed = False
        if TOKEN_PATH.exists():
            try:
                TOKEN_PATH.unlink()
                removed = True
            except Exception as exc:
                return json_response(self, 500, {"error": f"Could not remove saved Google sign-in token: {exc}"})
        return json_response(self, 200, {
            "message": "Google sign-in was cleared." if removed else "No saved Google sign-in token was found.",
            **google_setup_status(),
        })


def main():
    ensure_dirs()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), CalendarAssistantHandler)
    print(f"Calendar Assistant is running at http://127.0.0.1:{PORT}")
    print("Press Ctrl+C in this window when you are done.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCalendar Assistant stopped.")


if __name__ == "__main__":
    main()
