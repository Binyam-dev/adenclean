const menuButton = document.querySelector(".menu-toggle");
const navigation = document.querySelector("#primary-navigation");

function closeMenu() {
  if (!menuButton || !navigation) return;
  menuButton.setAttribute("aria-expanded", "false");
  menuButton.setAttribute("aria-label", "Open navigation");
  navigation.classList.remove("is-open");
}

if (menuButton && navigation) {
  menuButton.addEventListener("click", () => {
    const isOpen = menuButton.getAttribute("aria-expanded") === "true";
    menuButton.setAttribute("aria-expanded", String(!isOpen));
    menuButton.setAttribute("aria-label", isOpen ? "Open navigation" : "Close navigation");
    navigation.classList.toggle("is-open", !isOpen);
  });

  navigation.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
      menuButton.focus();
    }
  });

  document.addEventListener("click", (event) => {
    if (!navigation.contains(event.target) && !menuButton.contains(event.target)) closeMenu();
  });
}

const serviceTriggers = document.querySelectorAll(".service-trigger");
serviceTriggers.forEach((trigger) => {
  trigger.addEventListener("click", () => {
    const wasExpanded = trigger.getAttribute("aria-expanded") === "true";
    serviceTriggers.forEach((item) => {
      const panel = document.getElementById(item.getAttribute("aria-controls"));
      item.setAttribute("aria-expanded", "false");
      if (panel) panel.hidden = true;
    });

    if (!wasExpanded) {
      const panel = document.getElementById(trigger.getAttribute("aria-controls"));
      trigger.setAttribute("aria-expanded", "true");
      if (panel) panel.hidden = false;
    }
  });
});

const year = document.querySelector("#current-year");
if (year) year.textContent = new Date().getFullYear();

const revealTargets = document.querySelectorAll(
  ".intro-content, .section-heading, .service-item, .process-step, .contact-card"
);
revealTargets.forEach((element) => element.setAttribute("data-reveal", ""));

if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const revealObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  revealTargets.forEach((element) => revealObserver.observe(element));
} else {
  revealTargets.forEach((element) => element.classList.add("is-visible"));
}

function localDateString(date = new Date()) {
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 10);
}

document.querySelectorAll('input[type="date"]').forEach((input) => {
  input.min = localDateString();
});

function showFormFeedback(element, type, title, message, reference = "") {
  if (!element) return;

  element.classList.toggle("is-error", type === "error");
  element.setAttribute("role", type === "error" ? "alert" : "status");
  element.replaceChildren();

  const heading = document.createElement("strong");
  heading.textContent = title;
  const detail = document.createElement("p");
  detail.textContent = reference ? `${message} Reference: ${reference}` : message;
  element.append(heading, detail);
  element.focus();
}

async function submitWorkflowForm(form, endpoint, feedbackId, buildPayload, successTitle) {
  const feedback = document.getElementById(feedbackId);
  const submitButton = form.querySelector('button[type="submit"]');
  const originalButtonMarkup = submitButton.innerHTML;

  form.addEventListener("input", () => {
    if (feedback.classList.contains("is-error")) {
      feedback.classList.remove("is-error");
      feedback.replaceChildren();
      feedback.setAttribute("role", "status");
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const endTime = form.elements.namedItem("endTime");
    if (endTime) {
      const startTime = form.elements.namedItem("startTime");
      endTime.setCustomValidity(
        startTime.value && endTime.value && endTime.value <= startTime.value
          ? "End time must be later than start time."
          : ""
      );
    }

    if (!form.reportValidity()) return;

    const serviceCheckboxes = form.querySelectorAll('input[name="serviceTypes"]');
    if (serviceCheckboxes.length && !form.querySelector('input[name="serviceTypes"]:checked')) {
      showFormFeedback(
        feedback,
        "error",
        "Choose a service",
        "Select at least one service you offer."
      );
      serviceCheckboxes[0].focus();
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Saving…";
    form.setAttribute("aria-busy", "true");

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildPayload(new FormData(form))),
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || "The submission could not be saved.");
      }

      form.reset();
      showFormFeedback(
        feedback,
        "success",
        successTitle,
        `${result.message} Email updates are not connected in this preview.`,
        result.reference
      );
      if (endpoint === "/api/service-requests" && result.feedbackToken) {
        const detail = feedback.querySelector("p");
        const link = document.createElement("a");
        link.className = "feedback-private-link";
        link.href = `/feedback.html#token=${encodeURIComponent(result.feedbackToken)}`;
        link.textContent = "Open your private feedback link";
        const guidance = document.createElement("span");
        guidance.textContent = " Bookmark this link for after the service; anyone with it can submit feedback.";
        detail.append(document.createElement("br"), link, guidance);
      }
    } catch (error) {
      showFormFeedback(
        feedback,
        "error",
        "Submission not saved",
        error instanceof Error ? error.message : "Please try again."
      );
    } finally {
      submitButton.disabled = false;
      submitButton.innerHTML = originalButtonMarkup;
      form.removeAttribute("aria-busy");
    }
  });
}

const serviceRequestForm = document.querySelector("#service-request-form");
if (serviceRequestForm) {
  submitWorkflowForm(
    serviceRequestForm,
    "/api/service-requests",
    "request-feedback",
    (formData) => ({
      fullName: formData.get("fullName"),
      email: formData.get("email"),
      area: formData.get("area"),
      serviceType: formData.get("serviceType"),
      preferredDate: formData.get("preferredDate"),
      preferredTime: formData.get("preferredTime"),
      notes: formData.get("notes") || "",
      consent: formData.get("consent") === "on",
    }),
    "Inquiry saved"
  );
}

const cleanerAvailabilityForm = document.querySelector("#cleaner-availability-form");
if (cleanerAvailabilityForm) {
  submitWorkflowForm(
    cleanerAvailabilityForm,
    "/api/cleaner-availability",
    "availability-feedback",
    (formData) => ({
      fullName: formData.get("fullName"),
      email: formData.get("email"),
      area: formData.get("area"),
      serviceTypes: formData.getAll("serviceTypes"),
      availableDate: formData.get("availableDate"),
      startTime: formData.get("startTime"),
      endTime: formData.get("endTime"),
      consent: formData.get("consent") === "on",
    }),
    "Availability saved"
  );
}
