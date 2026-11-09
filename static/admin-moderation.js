// Reports tab: the review queue for reported jobs and offers. Loaded after admin.js and
// admin-vetting.js and shares their helpers. The server enforces every rule; this page only
// shows the actions. Apple expects a response within 24 hours, so the open count is on the tab.

const REPORT_KIND = { job: "Job notes", offer: "Offer message" };

async function actOnReport(report, action, button) {
  const warnings = {
    suspend_user: "Suspend this person? They cannot post, offer or sign in again until you restore them. A booking in progress continues.",
    cancel_booking_refund: "Cancel the booking and refund the customer in full? This cannot be undone.",
    remove_content: "Remove this text? A copy stays in the report.",
  };
  if (warnings[action] && !window.confirm(warnings[action])) return;
  button.disabled = true;
  try {
    const result = await parseResponse(await fetch(`/api/admin/moderation/${report.id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action }),
    }));
    await loadModeration();
    setNotice(dashboardNotice, result.warning ? `Done. ${result.warning}` : "Done.");
  } catch (error) {
    setNotice(dashboardNotice, error instanceof Error ? error.message : "Could not save that action.", true);
  } finally {
    button.disabled = false;
  }
}

function renderReports(queue) {
  recordList.replaceChildren();
  summary.replaceChildren();
  const count = element("div", "admin-summary-item");
  count.append(element("strong", "", String(queue.length)), element("span", "", "Open reports"));
  summary.append(count);
  setReportCount(queue.length);
  if (!queue.length) {
    recordList.append(element("p", "admin-empty", "No open reports. Reports are answered within 24 hours."));
    return;
  }
  queue.forEach((report) => {
    const card = element("article", "admin-record");
    const header = element("div", "admin-record-header");
    const heading = element("div");
    heading.append(element("h2", "", report.snapshot_name || "Unknown"),
      element("p", "admin-reference", `Report ${report.id} · ${friendlyTimestamp(report.created_at)}`));
    header.append(heading, element("span", "admin-status status-pre_adverse", report.reason_label));
    card.append(header);
    const details = element("dl", "admin-details");
    addDetail(details, "About", REPORT_KIND[report.target_kind] || report.target_kind);
    addDetail(details, "Reported text", report.snapshot_text || "(none saved)");
    addDetail(details, "Reporter's note", report.detail);
    addDetail(details, "Item status when reported", readableStatus(report.snapshot_status || "unknown"));
    addDetail(details, "Open reports about this person", String(report.open_reports_about_author));
    card.append(details);

    const controls = element("div", "admin-record-actions");
    const buttons = element("div", "admin-action-buttons");
    buttons.append(actionButton("Dismiss", true, (b) => actOnReport(report, "dismiss", b)));
    buttons.append(actionButton("Remove the text", false, (b) => actOnReport(report, "remove_content", b)));
    buttons.append(actionButton("Suspend this person", false, (b) => actOnReport(report, "suspend_user", b)));
    buttons.append(actionButton("Restore this person", true, (b) => actOnReport(report, "unsuspend_user", b)));
    if (report.target_kind === "offer") {
      buttons.append(actionButton("Cancel booking and refund", true, (b) => actOnReport(report, "cancel_booking_refund", b)));
    }
    controls.append(buttons);
    card.append(controls);
    recordList.append(card);
  });
}

function setReportCount(count) {
  const tab = document.querySelector('.admin-tab[data-record-type="moderation"]');
  if (tab) tab.textContent = count ? `Reports (${count})` : "Reports";
}

// Called when the dashboard opens, so the open count shows before the tab is chosen.
async function refreshReportCount() {
  try {
    const result = await parseResponse(await fetch("/api/admin/moderation", { cache: "no-store" }));
    setReportCount(result.queue.length);
  } catch {
    // The marketplace may be switched off; leave the tab label as it is.
  }
}

async function loadModeration() {
  if (dashboardSection.hidden) return;
  recordList.setAttribute("aria-busy", "true");
  setNotice(dashboardNotice, "");
  try {
    const result = await parseResponse(await fetch("/api/admin/moderation", { cache: "no-store" }));
    renderReports(result.queue);
  } catch (error) {
    recordList.replaceChildren();
    summary.replaceChildren();
    setNotice(dashboardNotice, error instanceof Error ? error.message : "Could not load reports.", true);
  } finally {
    recordList.removeAttribute("aria-busy");
  }
}
