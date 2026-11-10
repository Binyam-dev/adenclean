// Assign a customer request to a person. Loaded after admin.js and admin-vetting.js and
// uses their helpers. The status is not changed; the assignment is added to the history.

async function saveAssignment(record, input, button) {
  button.disabled = true;
  try {
    await parseResponse(await fetch("/api/admin/assignment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: record.id, assignedTo: input.value }),
    }));
    await loadRecords();
    setNotice(dashboardNotice, input.value.trim() ? `Assigned ${record.id} to ${input.value.trim()}.` : `Cleared the assignment on ${record.id}.`);
  } catch (error) {
    setNotice(dashboardNotice, error instanceof Error ? error.message : "Could not save the assignment.", true);
  } finally {
    button.disabled = false;
  }
}

function assignmentControl(record) {
  const wrapper = element("div", "admin-record-actions");
  const input = element("input");
  input.type = "text";
  input.maxLength = 100;
  input.value = record.assigned_to || "";
  input.placeholder = "Name of the person handling this";
  wrapper.append(labelled("Assigned to", input));
  const buttons = element("div", "admin-action-buttons");
  buttons.append(actionButton("Save assignment", true, (button) => saveAssignment(record, input, button)));
  wrapper.append(buttons);
  return wrapper;
}
