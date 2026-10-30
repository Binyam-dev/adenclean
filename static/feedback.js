const feedbackNotice = document.querySelector("#feedback-notice");
const feedbackLoading = document.querySelector("#feedback-loading");
const feedbackMissing = document.querySelector("#feedback-missing");
const feedbackWaiting = document.querySelector("#feedback-waiting");
const feedbackContent = document.querySelector("#feedback-content");
const feedbackService = document.querySelector("#feedback-service");
const reviewForm = document.querySelector("#review-form");
const issueForm = document.querySelector("#issue-form");
const reviewSubmitted = document.querySelector("#review-submitted");
const issueSubmitted = document.querySelector("#issue-submitted");
const token = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";

function setNotice(message, isError = false) {
  feedbackNotice.textContent = message;
  feedbackNotice.classList.toggle("is-error", isError);
  feedbackNotice.setAttribute("role", isError ? "alert" : "status");
}

function serviceLabel(serviceType) {
  return {
    routine: "Routine home cleaning",
    deep: "Deep cleaning",
    "move-in/move-out": "Move-in / move-out cleaning",
  }[serviceType] || "Cleaning service";
}

function formatDate(value) {
  if (!value) return "";
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
}

async function postFeedback(payload) {
  const response = await fetch("/api/customer-feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, token }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.ok) {
    throw new Error(result.error || "The request could not be completed.");
  }
  return result;
}

async function loadFeedback() {
  if (!token) {
    feedbackLoading.hidden = true;
    feedbackMissing.hidden = false;
    return;
  }

  try {
    const result = await postFeedback({ action: "lookup" });
    feedbackLoading.hidden = true;
    if (!result.ready) {
      feedbackWaiting.hidden = false;
      return;
    }

    feedbackContent.hidden = false;
    const service = document.createElement("strong");
    service.textContent = serviceLabel(result.serviceType);
    const date = document.createElement("span");
    date.textContent = result.preferredDate
      ? `Requested date: ${formatDate(result.preferredDate)}`
      : "";
    feedbackService.replaceChildren(service, date);

    reviewForm.hidden = result.reviewSubmitted;
    reviewSubmitted.hidden = !result.reviewSubmitted;
    issueForm.hidden = result.issueSubmitted;
    issueSubmitted.hidden = !result.issueSubmitted;
    if (result.issueSubmitted) {
      const statusMessages = {
        open: "Your report was received and is awaiting review. Reopen this private link later to check for updates.",
        in_review: "AdenClean is reviewing your report. Reopen this private link later to check for updates.",
        resolved: "AdenClean marked this report resolved. If you still need help, use the contact details above.",
      };
      issueSubmitted.textContent = statusMessages[result.issueStatus]
        || "Your report was received. Reopen this private link later to check for updates.";
    }
  } catch (error) {
    feedbackLoading.hidden = true;
    feedbackMissing.hidden = false;
    setNotice(error instanceof Error ? error.message : "This private link is unavailable.", true);
  }
}

async function submitFeedback(form, action) {
  if (!form.reportValidity()) return;
  const button = form.querySelector('button[type="submit"]');
  const originalMarkup = button.innerHTML;
  const formData = new FormData(form);
  const payload = {
    action,
    message: formData.get("message"),
    consent: formData.get("consent") === "on",
  };
  if (action === "review") payload.rating = Number(formData.get("rating"));

  button.disabled = true;
  button.textContent = "Sending…";
  form.setAttribute("aria-busy", "true");
  setNotice("");
  try {
    const result = await postFeedback(payload);
    form.reset();
    setNotice(result.message);
    await loadFeedback();
  } catch (error) {
    setNotice(error instanceof Error ? error.message : "Please try again.", true);
  } finally {
    button.disabled = false;
    button.innerHTML = originalMarkup;
    form.removeAttribute("aria-busy");
  }
}

reviewForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitFeedback(reviewForm, "review");
});

issueForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitFeedback(issueForm, "issue");
});

loadFeedback();
