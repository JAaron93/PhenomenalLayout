/** Zero-auth GCP cost and storage estimator (FR-01). */

export function initCostEstimator(root, api) {
  root.innerHTML = `
    <h2>1. Zero-Auth GCP Cost &amp; Storage Estimator</h2>
    <label for="cost-file">Upload Book PDF</label>
    <input id="cost-file" type="file" accept=".pdf" />
    <div class="row">
      <button id="cost-submit" class="primary">Calculate Budget Quote</button>
    </div>
    <div id="cost-result" class="result" hidden></div>
  `;

  const result = root.querySelector("#cost-result");

  root.querySelector("#cost-submit").addEventListener("click", async () => {
    const file = root.querySelector("#cost-file").files[0];
    result.hidden = false;
    result.textContent = file ? "Calculating…" : "Select a PDF first.";
    if (!file) {
      return;
    }
    try {
      const quote = await api.upload("/api/v1/cost/estimate", file);
      result.textContent = [
        `Total Pages: ${quote.total_pages}`,
        `File Size: ${quote.file_size_mb.toFixed(2)} MB`,
        `Document Translation ($0.080/page): $${quote.base_cost.toFixed(2)}`,
        `7-Day Staging Lifecycle: $${quote.staging_overhead_cost.toFixed(4)}`,
        `1-Month GCS Retention: $${quote.storage_cost_1mo.toFixed(4)}`,
        `12-Month GCS Archive: $${quote.storage_cost_12mo.toFixed(4)}`,
        `Always Free Tier (5 GB): ${quote.free_tier_covered ? "Covered" : "Exceeded"}`,
        `Total Estimated Cost: $${quote.total_estimate.toFixed(2)} ` +
          `(Tolerance Range: $${quote.tolerance_range[0].toFixed(2)} - $${quote.tolerance_range[1].toFixed(2)})`,
        `(Calculated in ${quote.estimation_time_sec.toFixed(1)} ms)`,
      ].join("\n");
    } catch (error) {
      result.textContent = `Quote failed: ${error.message}`;
    }
  });
}
