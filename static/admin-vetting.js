// Cleaner applicants: the review queue for identity and background checks. Loaded after
// admin.js and shares its helpers. The server enforces every rule (order of steps, written
// reasons, the waiting period, open disputes); this page only shows the next valid step.

const VETTING_STATUS = {
  in_review: "Ready for review",
  pre_adverse: "Pre-adverse notice sent",
};
const CHECK_LABEL = {
  not_started: "Not started", pending: "Waiting", invited: "Invited", verified: "Verified",
  failed: "Failed", clear: "Clear", consider: "Consider", suspended: "Suspended",
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function decideVetting(applicant, payload, button) {
  button.disabled = true;
  try {
    await parseResponse(await fetch(`/api/admin/vetting/${applicant.user_id}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }));
    await loadVetting();
    setNotice(dashboardNotice, `Updated ${applicant.name}.`); // after the reload, which clears the notice
  } catch (error) {
    setNotice(dashboardNotice, error instanceof Error ? error.message : "Could not save that decision.", true);
  } finally {
    button.disabled = false;
  }
}

function labelled(text, control) {
  const label = element("label", "", text);
  label.append(control);
  return label;
}

function noticeConfirmation(text) {
  const box = element("input");
  box.type = "checkbox";
  const label = element("label", "admin-confirm", "");
  label.append(box, document.createTextNode(` ${text}`));
  return { box, label };
}

function actionButton(label, secondary, onClick) {
  const button = element("button", secondary ? "admin-action-button is-secondary" : "admin-action-button", label);
  button.type = "button";
  button.addEventListener("click", () => onClick(button));
  return button;
}

function vettingControls(applicant, reasons) {
  const controls = element("div", "admin-record-actions");
  const buttons = element("div", "admin-action-buttons");
  const note = element("textarea");
  note.rows = 3;
  note.maxLength = 1000;
  const identityFailed = applicant.identity_status === "failed";
  const considered = applicant.background_status === "consider";
  const finished = applicant.identity_status === "verified" && ["clear", "consider"].includes(applicant.background_status);

  if (identityFailed) {
    controls.append(labelled("Reason for declining (optional)", note));
    buttons.append(actionButton("Decline: identity not verified", true,
      (b) => decideVetting(applicant, { action: "decline_identity", note: note.value }, b)));
  } else if (applicant.status === "in_review" && finished) {
    if (considered) {
      controls.append(element("p", "admin-help",
        "The report has a result to assess. Write the individualized assessment first: the offense, how long ago, and why it matters for work inside homes. Arrests without a conviction cannot be a reason."));
      controls.append(labelled("Individualized assessment (at least 20 characters)", note));
      const reason = element("select");
      Object.entries(reasons).forEach(([value, text]) => reason.append(new Option(text, value)));
      controls.append(labelled("Job-related reason (only if you will not approve)", reason));
      const sent = noticeConfirmation("I sent the pre-adverse notice from the Checkr dashboard, with the report and the Summary of Rights.");
      controls.append(sent.label);
      buttons.append(actionButton("Approve after assessment", false,
        (b) => decideVetting(applicant, { action: "approve", note: note.value }, b)));
      buttons.append(actionButton("Start pre-adverse action", true, (b) => {
        if (!sent.box.checked) return setNotice(dashboardNotice, "Send the notice from Checkr first, then tick the box.", true);
        decideVetting(applicant, { action: "pre_adverse", reason: reason.value, note: note.value, noticeSentViaCheckr: true }, b);
      }));
    } else {
      controls.append(labelled("Note (optional)", note));
      buttons.append(actionButton("Approve cleaner", false, (b) => decideVetting(applicant, { action: "approve", note: note.value }, b)));
    }
  } else if (applicant.status === "pre_adverse") {
    const deadline = applicant.dispute_deadline ? friendlyTimestamp(applicant.dispute_deadline) : "—";
    controls.append(element("p", "admin-help", `The cleaner can respond until ${deadline}.`));
    if (applicant.dispute_open) {
      controls.append(element("p", "admin-help", "The cleaner disputed the report. Review the dispute with Checkr, then resolve it here."));
      buttons.append(actionButton("Dispute resolved", false, (b) => decideVetting(applicant, { action: "resolve_dispute" }, b)));
    } else {
      controls.append(labelled("Assessment note (needed only to approve instead)", note));
      const sent = noticeConfirmation("I sent the final adverse action notice from the Checkr dashboard.");
      controls.append(sent.label);
      buttons.append(actionButton("Final decision: do not activate", true, (b) => {
        if (!sent.box.checked) return setNotice(dashboardNotice, "Send the final notice from Checkr first, then tick the box.", true);
        decideVetting(applicant, { action: "final_adverse", noticeSentViaCheckr: true }, b);
      }));
      buttons.append(actionButton("Approve instead", false, (b) => decideVetting(applicant, { action: "approve", note: note.value }, b)));
    }
  } else {
    controls.append(element("p", "admin-help", "Waiting for the cleaner to finish their checks."));
  }
  if (buttons.childElementCount) controls.append(buttons);
  return controls;
}

function renderVetting(queue, reasons) {
  recordList.replaceChildren();
  summary.replaceChildren();
  [["in_review", "Ready for review"], ["pre_adverse", "Pre-adverse sent"]].forEach(([status, label]) => {
    const item = element("div", "admin-summary-item");
    item.append(element("strong", "", String(queue.filter((q) => q.status === status).length)), element("span", "", label));
    summary.append(item);
  });
  if (!queue.length) {
    recordList.append(element("p", "admin-empty", "No cleaner applications need review."));
    return;
  }
  queue.forEach((applicant) => {
    const card = element("article", "admin-record");
    const header = element("div", "admin-record-header");
    const heading = element("div");
    heading.append(element("h2", "", applicant.name), element("p", "admin-reference", `Applicant ${applicant.user_id}`));
    header.append(heading, element("span", `admin-status status-${applicant.status}`, VETTING_STATUS[applicant.status] || readableStatus(applicant.status)));
    card.append(header);
    const details = element("dl", "admin-details");
    addDetail(details, "Identity (Stripe)", CHECK_LABEL[applicant.identity_status]);
    addDetail(details, "Background (Checkr)", CHECK_LABEL[applicant.background_status]);
    addDetail(details, "Disclosure signed", friendlyTimestamp(applicant.consent_at));
    addDetail(details, "Checkr report", applicant.report_ref ? `${applicant.report_ref} (read it in Checkr)` : "—");
    if (applicant.status === "pre_adverse") addDetail(details, "Dispute", applicant.dispute_open ? "Open" : "None");
    card.append(details, vettingControls(applicant, reasons));
    recordList.append(card);
  });
}

async function loadVetting() {
  if (dashboardSection.hidden) return;
  recordList.setAttribute("aria-busy", "true");
  setNotice(dashboardNotice, "");
  try {
    const result = await parseResponse(await fetch("/api/admin/vetting", { cache: "no-store" }));
    renderVetting(result.queue, result.reasons);
  } catch (error) {
    recordList.replaceChildren();
    summary.replaceChildren();
    setNotice(dashboardNotice, error instanceof Error ? error.message : "Could not load applicants.", true);
  } finally {
    recordList.removeAttribute("aria-busy");
  }
}
