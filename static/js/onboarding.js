/** Interactive GCP onboarding walkthrough modal (FR-02). */

export function initOnboarding(root, api) {
  root.innerHTML = `
    <button id="onboarding-open">📘 2. Interactive GCP Onboarding Walkthrough</button>
    <div id="onboarding-modal" class="modal" hidden>
      <h2>GCP Onboarding Walkthrough</h2>
      <ol id="onboarding-steps"></ol>
      <label for="gcloud-script">Setup script</label>
      <pre id="gcloud-script"></pre>
      <div class="row">
        <button id="onboarding-copy">Copy script</button>
        <button id="onboarding-close">Close</button>
      </div>
    </div>
  `;

  const modal = root.querySelector("#onboarding-modal");
  const stepsList = root.querySelector("#onboarding-steps");

  root.querySelector("#onboarding-open").addEventListener("click", async () => {
    try {
      const guide = await api.getJson("/api/v1/byok/onboarding-guide");
      stepsList.innerHTML = "";
      for (const step of guide.steps ?? []) {
        const item = document.createElement("li");
        item.className = "onboarding-step";
        const title = document.createElement("strong");
        title.textContent = `${step.step_number}. ${step.title}`;
        const description = document.createElement("p");
        description.textContent = step.description ?? "";
        item.append(title, description);
        stepsList.append(item);
      }
      root.querySelector("#gcloud-script").textContent = guide.gcloud_script ?? "";
      modal.hidden = false;
    } catch (error) {
      modal.hidden = false;
      stepsList.textContent = `Failed to load guide: ${error.message}`;
    }
  });

  root.querySelector("#onboarding-copy").addEventListener("click", () => {
    const script = root.querySelector("#gcloud-script").textContent;
    navigator.clipboard?.writeText(script).catch(() => copyFallback(script));
  });

  root.querySelector("#onboarding-close").addEventListener("click", () => {
    modal.hidden = true;
  });
}

function copyFallback(text) {
  const area = document.createElement("textarea");
  area.value = text;
  document.body.append(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}
