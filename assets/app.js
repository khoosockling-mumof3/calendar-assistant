const uploadForm = document.querySelector("#uploadForm");
const fileInput = document.querySelector("#fileInput");
const statusEl = document.querySelector("#status");
const calendarStatusEl = document.querySelector("#calendarStatus");
const eventsEl = document.querySelector("#events");
const draftsEl = document.querySelector("#drafts");
const saveDraftButton = document.querySelector("#saveDraft");
const refreshDraftsButton = document.querySelector("#refreshDrafts");
const duplicateStartInput = document.querySelector("#duplicateStart");
const duplicateEndInput = document.querySelector("#duplicateEnd");
const searchDuplicatesButton = document.querySelector("#searchDuplicates");
const setupForm = document.querySelector("#setupForm");
const credentialsInput = document.querySelector("#credentialsInput");
const setupStatusEl = document.querySelector("#setupStatus");
const signOutGoogleButton = document.querySelector("#signOutGoogle");

let currentEvents = [];

const fields = [
  ["title", "Title", "input"],
  ["date", "Date", "input"],
  ["start_time", "Start time", "input"],
  ["end_time", "End time", "input"],
  ["location", "Location", "input"],
  ["change_type", "New, cancellation, or reschedule", "select"],
  ["google_calendar_id", "Google calendar", "input"],
  ["google_event_id", "Google event ID for updates", "input"],
  ["description", "Description", "textarea"],
  ["notes", "Review notes", "textarea"],
];

function setStatus(message, tone = "") {
  statusEl.textContent = message;
  statusEl.className = `status ${tone}`.trim();
}

function renderSetupStatus(status) {
  if (!status) {
    setupStatusEl.textContent = "Google setup has not been checked yet.";
    return;
  }
  const credentialText = status.credentials_configured
    ? `Credentials saved${status.client_id_hint ? ` (${status.client_id_hint})` : ""}.`
    : "No Google credentials saved yet.";
  const tokenText = status.token_exists
    ? "Google sign-in is saved."
    : "Google sign-in will open when Calendar is first used.";
  setupStatusEl.textContent = `${credentialText} ${tokenText}`;
}

async function loadSetupStatus() {
  try {
    const response = await fetch("/api/setup-status");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not check Google setup.");
    renderSetupStatus(payload);
  } catch (error) {
    setupStatusEl.textContent = error.message;
  }
}

function renderCalendarStatus(sync) {
  if (!sync) {
    calendarStatusEl.className = "calendar-status empty-status";
    calendarStatusEl.innerHTML = `
      <h2>Google Calendar Status</h2>
      <p>No Google Calendar updates yet.</p>
    `;
    return;
  }

  const results = sync.results || [];
  const changed = results.filter((item) => ["created", "updated"].includes(item.status));
  const skipped = results.filter((item) => item.status && item.status.startsWith("skipped"));
  const failed = sync.synced === false && sync.message && !sync.message.includes("not requested");
  calendarStatusEl.className = `calendar-status ${failed ? "status-failed" : changed.length ? "status-ok" : "empty-status"}`;

  const rows = results.length ? results.map((item) => `
    <li>
      <strong>${escapeHtml(item.title || "Untitled event")}</strong>
      <span>${escapeHtml(item.status || "unknown")}</span>
      ${item.html_link ? `<a href="${escapeHtml(item.html_link)}" target="_blank" rel="noreferrer">Open</a>` : ""}
    </li>
  `).join("") : "<li>No events were created or updated.</li>";
  const latestLink = sync.latest_event_link || [...results].reverse().find((item) => ["created", "updated"].includes(item.status) && item.html_link)?.html_link || "";

  calendarStatusEl.innerHTML = `
    <h2>Google Calendar Status</h2>
    <p>${escapeHtml(sync.message || "No Google Calendar status message.")}</p>
    ${latestLink ? `<p><a class="latest-event-link" href="${escapeHtml(latestLink)}" target="_blank" rel="noreferrer">Open latest Google Calendar event</a></p>` : ""}
    <div class="calendar-status-counts">
      <span>${changed.length} created/updated</span>
      <span>${skipped.length} skipped</span>
    </div>
    <ul>${rows}</ul>
  `;
}

function openLatestGoogleEvent(sync) {
  const results = sync?.results || [];
  const latestLink = sync?.latest_event_link || [...results].reverse().find((item) => ["created", "updated"].includes(item.status) && item.html_link)?.html_link;
  if (latestLink) {
    window.open(latestLink, "_blank", "noopener");
  }
}

function renderEvents(events) {
  currentEvents = events;
  saveDraftButton.disabled = events.length === 0;
  searchDuplicatesButton.disabled = events.length === 0;
  if (!events.length) {
    eventsEl.className = "events empty-state";
    eventsEl.textContent = "Upload files to create draft event details for review.";
    return;
  }

  eventsEl.className = "events";
  eventsEl.innerHTML = "";
  events.forEach((event, index) => {
    const card = document.createElement("article");
    card.className = "event-card";
    const heading = document.createElement("div");
    heading.className = "event-heading";
    heading.innerHTML = `
      <div>
        <h3>Event ${index + 1}</h3>
        <p>${escapeHtml(event.source_file || "Uploaded file")} · ${escapeHtml(event.confidence || "needs review")}</p>
      </div>
      <button type="button" data-remove="${index}">Remove</button>
    `;
    card.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "field-grid";
    fields.forEach(([key, label, type]) => {
      const wrap = document.createElement("label");
      wrap.textContent = label;
      let input;
      if (type === "textarea") {
        input = document.createElement("textarea");
        input.rows = key === "description" ? 5 : 3;
      } else if (type === "select") {
        input = document.createElement("select");
        ["new event", "cancellation", "reschedule"].forEach((optionValue) => {
          const option = document.createElement("option");
          option.value = optionValue;
          option.textContent = optionValue;
          input.appendChild(option);
        });
      } else {
        input = document.createElement("input");
      }
      input.value = event[key] || "";
      input.dataset.index = index;
      input.dataset.key = key;
      wrap.appendChild(input);
      grid.appendChild(wrap);
    });
    card.appendChild(grid);
    card.appendChild(renderDuplicateReview(event, index));
    eventsEl.appendChild(card);
  });
}

function renderDuplicateReview(event, index) {
  const panel = document.createElement("div");
  panel.className = "duplicate-review";
  const matches = event.google_duplicate_matches || [];
  if (!matches.length) {
    panel.innerHTML = `<p>No duplicate search result for this event yet.</p>`;
    return panel;
  }

  const best = matches[0];
  const selectedAction = event.google_duplicate_action || "skip";
  const selectedMatchId = event.google_duplicate_match_id || best.id || "";
  const matchOptions = matches.map((match) => {
    const label = `${match.title} | ${match.start} | ${match.location || "no location"} | score ${match.score}`;
    return `<option value="${escapeHtml(match.id)}">${escapeHtml(label)}</option>`;
  }).join("");
  panel.innerHTML = `
    <div>
      <strong>Possible duplicate found</strong>
      <p>${escapeHtml(best.title)} · ${escapeHtml(best.start)} · ${escapeHtml(best.location || "no location")} · ${escapeHtml(best.reasons.join(", "))}</p>
    </div>
    <div class="duplicate-controls">
      <label>
        Existing event
        <select data-index="${index}" data-key="google_duplicate_match_id">
          ${matchOptions}
        </select>
      </label>
      <label>
        Google Calendar choice
        <select data-index="${index}" data-key="google_duplicate_action">
          <option value="update_existing">Update existing event</option>
          <option value="create_new">Create new event</option>
          <option value="skip">Skip this event</option>
        </select>
      </label>
    </div>
  `;
  panel.querySelector('[data-key="google_duplicate_action"]').value = selectedAction;
  panel.querySelector('[data-key="google_duplicate_match_id"]').value = selectedMatchId;
  return panel;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;",
  }[char]));
}

function updateEventField(event) {
  const index = event.target.dataset.index;
  const key = event.target.dataset.key;
  if (index === undefined || !key) return;
  currentEvents[Number(index)][key] = event.target.value;
  if (key === "google_duplicate_action" || key === "google_duplicate_match_id") {
    const item = currentEvents[Number(index)];
    const selectedMatch = (item.google_duplicate_matches || []).find((match) => match.id === item.google_duplicate_match_id) || (item.google_duplicate_matches || [])[0] || {};
    if (!item.google_duplicate_match_id && selectedMatch.id) item.google_duplicate_match_id = selectedMatch.id;
    item.google_duplicate_match = item.google_duplicate_action === "update_existing" ? selectedMatch : {};
    item.google_event_id = item.google_duplicate_action === "update_existing" ? (selectedMatch.id || item.google_event_id || "") : "";
    renderEvents(currentEvents);
  }
}

eventsEl.addEventListener("input", updateEventField);
eventsEl.addEventListener("change", updateEventField);

eventsEl.addEventListener("click", (event) => {
  const removeIndex = event.target.dataset.remove;
  if (removeIndex === undefined) return;
  currentEvents.splice(Number(removeIndex), 1);
  renderEvents(currentEvents);
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) {
    setStatus("Choose at least one file first.", "warn");
    return;
  }
  const formData = new FormData();
  [...fileInput.files].forEach((file) => formData.append("files", file));
  setStatus("Reviewing files...");
  try {
    const response = await fetch("/api/upload", { method: "POST", body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Upload failed.");
    renderCalendarStatus(null);
    renderEvents(payload.events || []);
    setStatus(`Saved draft JSON: ${payload.draft_path}`, "ok");
    loadDrafts();
  } catch (error) {
    setStatus(error.message, "warn");
  }
});

saveDraftButton.addEventListener("click", async () => {
  setStatus("Saving edited draft and syncing to Google Calendar...");
  renderCalendarStatus({
    synced: false,
    message: "Saving the JSON draft and syncing selected events to Google Calendar...",
    results: [],
  });
  try {
    const response = await fetch("/api/save-draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: currentEvents }),
    });
    const payload = await response.json();
    if (!response.ok) {
      if (payload.google_calendar_sync) renderCalendarStatus(payload.google_calendar_sync);
      throw new Error(payload.google_calendar_sync?.message || payload.error || "Could not save draft.");
    }
    const syncMessage = payload.google_calendar_sync?.message ? ` ${payload.google_calendar_sync.message}` : "";
    renderCalendarStatus(payload.google_calendar_sync);
    openLatestGoogleEvent(payload.google_calendar_sync);
    setStatus(`Saved edited draft JSON: ${payload.draft_path}.${syncMessage}`, "ok");
    loadDrafts();
  } catch (error) {
    setStatus(error.message, "warn");
  }
});

searchDuplicatesButton.addEventListener("click", async () => {
  if (!currentEvents.length) {
    setStatus("Upload or review events before searching for duplicates.", "warn");
    return;
  }
  const startDate = duplicateStartInput.value;
  const endDate = duplicateEndInput.value;
  if (!startDate || !endDate) {
    setStatus("Choose a start and end date for the duplicate search.", "warn");
    return;
  }
  setStatus("Searching Google Calendar for similar events. You may need to sign in.");
  try {
    const response = await fetch("/api/search-duplicates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: currentEvents, start_date: startDate, end_date: endDate }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Duplicate search failed.");
    let found = 0;
    (payload.matches || []).forEach((result) => {
      const item = currentEvents[result.index];
      if (!item) return;
      item.google_duplicate_matches = result.matches || [];
      if (item.google_duplicate_matches.length) {
        found += 1;
        item.google_duplicate_action = "skip";
        item.google_duplicate_match_id = item.google_duplicate_matches[0].id || "";
        item.google_duplicate_match = item.google_duplicate_matches[0];
        item.google_event_id = item.google_duplicate_matches[0].id || "";
      } else {
        item.google_duplicate_action = "create_new";
        item.google_duplicate_match_id = "";
        item.google_duplicate_match = {};
        item.google_duplicate_matches = [];
        item.google_event_id = "";
      }
    });
    renderEvents(currentEvents);
    setStatus(`Duplicate search complete. ${found} event(s) have possible matches.`, "ok");
  } catch (error) {
    setStatus(error.message, "warn");
  }
});

setupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!credentialsInput.files.length) {
    setStatus("Choose a Google credentials JSON file first.", "warn");
    return;
  }
  const formData = new FormData();
  formData.append("credentials", credentialsInput.files[0]);
  setStatus("Saving Google credentials...");
  try {
    const response = await fetch("/api/setup-credentials", { method: "POST", body: formData });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not save Google credentials.");
    renderSetupStatus(payload);
    credentialsInput.value = "";
    setStatus(payload.message || "Google credentials saved.", "ok");
  } catch (error) {
    setStatus(error.message, "warn");
  }
});

signOutGoogleButton.addEventListener("click", async () => {
  setStatus("Clearing saved Google sign-in...");
  try {
    const response = await fetch("/api/sign-out-google", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not clear Google sign-in.");
    renderSetupStatus(payload);
    setStatus(payload.message || "Google sign-in cleared.", "ok");
  } catch (error) {
    setStatus(error.message, "warn");
  }
});

async function loadDrafts() {
  const response = await fetch("/api/drafts");
  const payload = await response.json();
  const drafts = payload.drafts || [];
  if (!drafts.length) {
    draftsEl.textContent = "No JSON drafts saved yet.";
    return;
  }
  draftsEl.innerHTML = "";
  drafts.forEach((draft) => {
    const item = document.createElement("div");
    item.className = "draft-item";
    item.innerHTML = `
      <strong>${escapeHtml(draft.name)}</strong>
      <span>${escapeHtml(String(draft.event_count))} event(s)</span>
      <small>${escapeHtml(draft.path)}</small>
    `;
    draftsEl.appendChild(item);
  });
}

refreshDraftsButton.addEventListener("click", loadDrafts);
loadSetupStatus();
loadDrafts();
