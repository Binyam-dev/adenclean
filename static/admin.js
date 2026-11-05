const loginSection = document.querySelector("#admin-login");
const dashboardSection = document.querySelector("#admin-dashboard");
const loginForm = document.querySelector("#admin-login-form");
const loginNotice = document.querySelector("#admin-notice");
const dashboardNotice = document.querySelector("#dashboard-notice");
const emailInput = document.querySelector("#admin-email");
const passwordInput = document.querySelector("#admin-password");
const recordList = document.querySelector("#admin-record-list");
const summary = document.querySelector("#admin-summary");
const statusFilter = document.querySelector("#admin-status-filter");
const tabs = document.querySelectorAll(".admin-tab");

let recordType = "requests";
let activeRecords = [];

function setNotice(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("is-error", isError);
}

function showLogin(message = "", allowPasswordEntry = false) {
  dashboardSection.hidden = true;
  loginSection.hidden = false;
  loginForm.hidden = !allowPasswordEntry;
  setNotice(loginNotice, message, message.toLowerCase().includes("incorrect"));
  if (loginForm.hidden) return;
  (emailInput.value ? passwordInput : emailInput).focus();
}

function showDashboard() {
  loginSection.hidden = true;
  dashboardSection.hidden = false;
}

async function parseResponse(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) {
    throw new Error(result.error || "The request could not be completed.");
  }
  return result;
}

async function checkSession() {
  try {
    const response = await fetch("/api/admin/session", { cache: "no-store" });
    const result = await parseResponse(response);
    if (result.configured === false) {
      showLogin(result.message || "Admin access is not set up yet.");
      return;
    }
    if (result.authenticated === false) {
      showLogin("Sign in with your admin email and password.", true);
      return;
    }
    showDashboard();
    await loadRecords();
  } catch (error) {
    showLogin(error instanceof Error ? error.message : "Admin access is unavailable.");
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!loginForm.reportValidity()) return;
  const submitButton = loginForm.querySelector('button[type="submit"]');
  submitButton.disabled = true;
  submitButton.textContent = "Signing in…";

  try {
    await parseResponse(await fetch("/api/admin/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: emailInput.value, password: passwordInput.value }),
    }));
    passwordInput.value = "";
    showDashboard();
    await loadRecords();
  } catch (error) {
    showLogin(error instanceof Error ? error.message : "Sign-in failed.", true);
    passwordInput.value = "";
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Sign in ↗";
  }
});

document.querySelector("#admin-logout").addEventListener("click", async () => {
  try {
    await fetch("/api/admin/logout", { method: "POST" });
  } finally {
    recordList.replaceChildren();
    summary.replaceChildren();
    showLogin("You have signed out.", true);
  }
});

document.querySelector("#admin-refresh").addEventListener("click", loadRecords);
statusFilter.addEventListener("change", loadRecords);

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    recordType = tab.dataset.recordType;
    tabs.forEach((item) => {
      const selected = item === tab;
      item.classList.toggle("is-active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    configureStatusOptions();
    loadRecords();
  });
});

function configureStatusOptions() {
  const statusesByType = {
    requests: ["all", "pending", "approved", "declined", "completed", "cancelled"],
    availability: ["all", "pending", "approved", "declined"],
    reviews: ["all", "new", "reviewed"],
    issues: ["all", "open", "in_review", "resolved"],
    vetting: ["all"],
  };
  statusFilter.closest("label").hidden = recordType === "vetting";
  const labels = {
    all: "All statuses",
    pending: "Pending",
    approved: "Approved",
    declined: "Declined",
    completed: "Completed",
    cancelled: "Cancelled",
    new: "New",
    reviewed: "Reviewed",
    open: "Open",
    in_review: "In review",
    resolved: "Resolved",
  };
  const statuses = statusesByType[recordType] || statusesByType.requests;
  const previousValue = statusFilter.value;
  statusFilter.replaceChildren();
  statuses.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = labels[value];
    statusFilter.append(option);
  });
  statusFilter.value = statuses.includes(previousValue) ? previousValue : "all";
}

async function loadRecords() {
  if (dashboardSection.hidden) return;
  if (recordType === "vetting") return loadVetting();
  recordList.setAttribute("aria-busy", "true");
  setNotice(dashboardNotice, "");
  try {
    const query = new URLSearchParams({ type: recordType, status: statusFilter.value });
    const result = await parseResponse(
      await fetch(`/api/admin/records?${query}`, { cache: "no-store" })
    );
    activeRecords = result.records;
    renderSummary(result.counts);
    renderRecords(result.records);
  } catch (error) {
    setNotice(
      dashboardNotice,
      error instanceof Error ? error.message : "Could not load submissions.",
      true
    );
  } finally {
    recordList.removeAttribute("aria-busy");
  }
}

function renderSummary(counts) {
  summary.replaceChildren();
  const labelsByType = {
    requests: [["pending", "Pending"], ["approved", "Approved"], ["declined", "Declined"], ["completed", "Completed"]],
    availability: [["pending", "Pending"], ["approved", "Approved"], ["declined", "Declined"]],
    reviews: [["new", "New"], ["reviewed", "Reviewed"]],
    issues: [["open", "Open"], ["in_review", "In review"], ["resolved", "Resolved"]],
  };
  const labels = labelsByType[recordType] || labelsByType.requests;
  labels.forEach(([status, label]) => {
    const item = document.createElement("div");
    item.className = "admin-summary-item";
    const count = document.createElement("strong");
    count.textContent = String(counts[status] || 0);
    const caption = document.createElement("span");
    caption.textContent = label;
    item.append(count, caption);
    summary.append(item);
  });
}

function addDetail(container, label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "admin-detail";
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value || "—";
  wrapper.append(term, description);
  container.append(wrapper);
}

function friendlyDate(value) {
  if (!value) return "—";
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function friendlyTimestamp(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function readableStatus(value) {
  return value.replaceAll("_", " ").replace(/^./, (letter) => letter.toUpperCase());
}

function actionOptions(record) {
  if (recordType === "availability") {
    if (record.status === "pending") {
      return [["approved", "Approve availability"], ["declined", "Decline"]];
    }
    if (record.status === "declined") return [["pending", "Reopen"]];
    return [];
  }
  if (recordType === "reviews") {
    return record.status === "new" ? [["reviewed", "Mark reviewed"]] : [];
  }
  if (recordType === "issues") {
    if (record.status === "open") return [["in_review", "Start review"], ["resolved", "Resolve issue"]];
    if (record.status === "in_review") return [["open", "Return to open"], ["resolved", "Resolve issue"]];
    if (record.status === "resolved") return [["in_review", "Reopen issue"]];
    return [];
  }
  if (record.status === "pending") {
    return [["approved", "Approve for follow-up"], ["declined", "Decline"], ["cancelled", "Cancel"]];
  }
  if (record.status === "approved") {
    return [["completed", "Mark complete"], ["cancelled", "Cancel"], ["pending", "Return to pending"]];
  }
  if (record.status === "declined" || record.status === "cancelled") return [["pending", "Reopen"]];
  return [];
}

async function changeStatus(record, nextStatus, noteInput, button) {
  if (nextStatus === "declined" && !window.confirm("Decline this submission? You can reopen it later.")) {
    return;
  }
  button.disabled = true;
  try {
    await parseResponse(await fetch("/api/admin/records", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type: recordType,
        id: record.id,
        expectedStatus: record.status,
        status: nextStatus,
        note: noteInput.value,
      }),
    }));
    setNotice(dashboardNotice, `Updated ${record.id} to ${readableStatus(nextStatus)}.`);
    await loadRecords();
  } catch (error) {
    setNotice(
      dashboardNotice,
      error instanceof Error ? error.message : "Could not update this submission.",
      true
    );
  } finally {
    button.disabled = false;
  }
}

function renderRecords(records) {
  recordList.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("p");
    empty.className = "admin-empty";
    empty.textContent = "No submissions match this filter.";
    recordList.append(empty);
    return;
  }

  records.forEach((record) => {
    const card = document.createElement("article");
    card.className = "admin-record";
    const header = document.createElement("div");
    header.className = "admin-record-header";
    const heading = document.createElement("div");
    const name = document.createElement("h2");
    name.textContent = record.full_name;
    const reference = document.createElement("p");
    reference.className = "admin-reference";
    reference.textContent = record.request_id
      ? `Feedback ${record.id} · Request ${record.request_id} · Submitted ${friendlyTimestamp(record.created_at)}`
      : `Reference ${record.id} · Submitted ${friendlyTimestamp(record.created_at)}`;
    heading.append(name, reference);
    const badge = document.createElement("span");
    badge.className = `admin-status status-${record.status}`;
    badge.textContent = readableStatus(record.status);
    header.append(heading, badge);
    card.append(header);

    const details = document.createElement("dl");
    details.className = "admin-details";
    addDetail(details, "Email", record.email);
    addDetail(details, "Area", record.area);
    if (recordType === "requests") {
      const serviceLabels = {
        routine: "Routine home cleaning",
        deep: "Deep cleaning",
        "move-in/move-out": "Move-in / move-out",
      };
      addDetail(details, "Service", serviceLabels[record.service_type] || record.service_type);
      addDetail(details, "Preferred date", friendlyDate(record.preferred_date));
      addDetail(details, "Preferred time", record.preferred_time);
      if (record.notes) addDetail(details, "Customer note", record.notes);
    } else if (recordType === "availability") {
      let cleanerServices = record.service_types;
      try {
        cleanerServices = JSON.parse(record.service_types)
          .map((service) => ({
            routine: "Routine",
            deep: "Deep clean",
            "move-in/move-out": "Move-in / move-out",
          }[service] || service))
          .join(", ");
      } catch {
        // Display the stored value as text if an old record is malformed.
      }
      addDetail(details, "Services offered", cleanerServices);
      addDetail(details, "Available date", friendlyDate(record.available_date));
      addDetail(details, "Time window", `${record.start_time}–${record.end_time}`);
    } else {
      const serviceLabels = {
        routine: "Routine home cleaning",
        deep: "Deep cleaning",
        "move-in/move-out": "Move-in / move-out",
      };
      addDetail(details, "Service", serviceLabels[record.service_type] || record.service_type);
      addDetail(details, "Service date", friendlyDate(record.preferred_date));
      if (recordType === "reviews") addDetail(details, "Rating", `${record.rating} / 5`);
      addDetail(details, recordType === "reviews" ? "Customer review" : "Reported issue", record.message);
    }
    card.append(details);

    const historyHeading = document.createElement("h3");
    historyHeading.className = "admin-history-heading";
    historyHeading.textContent = "Status history";
    const historyList = document.createElement("ol");
    historyList.className = "admin-history";
    (record.history || []).forEach((event) => {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = `${readableStatus(event.newStatus)} · ${friendlyTimestamp(event.createdAt)}`;
      const description = document.createElement("span");
      description.textContent = event.note || `Updated by ${event.actor}.`;
      item.append(title, description);
      historyList.append(item);
    });
    card.append(historyHeading, historyList);

    const actions = actionOptions(record);
    if (actions.length) {
      const controls = document.createElement("div");
      controls.className = "admin-record-actions";
      const noteLabel = document.createElement("label");
      noteLabel.textContent = "Internal note (optional)";
      const noteInput = document.createElement("input");
      noteInput.type = "text";
      noteInput.maxLength = 240;
      noteInput.placeholder = "Not sent to the customer";
      noteLabel.append(noteInput);
      controls.append(noteLabel);

      const buttons = document.createElement("div");
      buttons.className = "admin-action-buttons";
      actions.forEach(([status, label]) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = status === "declined" || status === "cancelled"
          ? "admin-action-button is-secondary"
          : "admin-action-button";
        button.textContent = label;
        button.addEventListener("click", () => changeStatus(record, status, noteInput, button));
        buttons.append(button);
      });
      controls.append(buttons);
      card.append(controls);
    }
    recordList.append(card);
  });
}

checkSession();
