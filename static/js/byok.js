/** BYOK credential panel (FR-03): JSON-body POST, query-based validate/clear. */

export function initByok(root, api) {
  root.innerHTML = `
    <h2>3. Bring Your Own Key (BYOK) Setup</h2>
    <label for="byok-project">GCP Project ID</label>
    <input id="byok-project" autocomplete="off" />
    <label for="byok-bucket">GCS Bucket Name</label>
    <input id="byok-bucket" autocomplete="off" />
    <label for="byok-sa">Service Account JSON</label>
    <textarea id="byok-sa" rows="3"></textarea>
    <div class="row">
      <button id="byok-save" class="primary">Set Credentials</button>
      <button id="byok-validate">Validate Credentials</button>
      <button id="byok-clear">Clear Credentials</button>
    </div>
    <div id="byok-result" class="result" hidden></div>
  `;

  const result = root.querySelector("#byok-result");

  const show = (text) => {
    result.hidden = false;
    result.textContent = text;
  };

  root.querySelector("#byok-save").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    try {
      const outcome = await api.postJson("/api/v1/byok/credentials", {
        user_id: userId,
        project_id: root.querySelector("#byok-project").value,
        bucket_name: root.querySelector("#byok-bucket").value,
        sa_json: root.querySelector("#byok-sa").value,
      });
      show(
        `Credentials stored. Translation API: ${ok(outcome.translation_api_ok)} — Storage bucket: ${ok(outcome.storage_bucket_ok)}`
      );
    } catch (error) {
      show(`Credential setup failed: ${error.message}`);
    }
  });

  root.querySelector("#byok-validate").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    try {
      const outcome = await api.getJson("/api/v1/byok/validate", { query: { user_id: userId } });
      show(`Validation: valid=${ok(outcome.is_valid)}`);
    } catch (error) {
      show(`Validation failed: ${error.message}`);
    }
  });

  root.querySelector("#byok-clear").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    try {
      await api.delete("/api/v1/byok/credentials", { query: { user_id: userId } });
      show("Credentials cleared.");
    } catch (error) {
      show(`Clear failed: ${error.message}`);
    }
  });
}

function ok(value) {
  return value ? "OK" : "FAILED";
}
