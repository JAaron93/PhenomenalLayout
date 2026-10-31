/** Pre-scan, Fraktur badge, neologisms, and terminology memory (FR-04). */

export function initPrescan(root, api) {
  root.innerHTML = `
    <h2>4. Pre-Scan &amp; Fraktur Script Confidence</h2>
    <label for="prescan-file">Select Book PDF</label>
    <input id="prescan-file" type="file" accept=".pdf" />
    <div class="row">
      <button id="prescan-run" class="primary">Run Pre-Scan Assessment</button>
      <button id="vocab-refresh">Refresh saved terminology</button>
      <a id="vocab-export" hidden>Export TSV</a>
    </div>
    <div id="prescan-result" class="result" hidden></div>
    <h3>Terminology memory</h3>
    <div class="row">
      <div>
        <label for="vocab-term">German term</label>
        <input id="vocab-term" autocomplete="off" />
      </div>
      <div>
        <label for="vocab-translation">Preferred translation</label>
        <input id="vocab-translation" autocomplete="off" />
      </div>
      <button id="vocab-save">Save term</button>
    </div>
    <ul id="vocab-list"></ul>
    <label for="vocab-import">Import TSV (de⇥en per line)</label>
    <textarea id="vocab-import" rows="2"></textarea>
    <button id="vocab-import-btn">Import</button>
  `;

  const result = root.querySelector("#prescan-result");
  const vocabList = root.querySelector("#vocab-list");
  const exportLink = root.querySelector("#vocab-export");

  const showResult = (text) => {
    result.hidden = false;
    result.textContent = text;
  };

  root.querySelector("#prescan-run").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    const file = root.querySelector("#prescan-file").files[0];
    if (!file) {
      showResult("Select a PDF first.");
      return;
    }
    showResult("Pre-scanning…");
    try {
      const scan = await api.upload("/api/v1/book/pre-scan", file, { user_id: userId });
      const rawNeologisms = scan.detected_neologisms ?? [];
      const neologismList = rawNeologisms
        .map((n) => (typeof n === "string" ? n : n.term ?? n.german_term ?? JSON.stringify(n)))
        .filter(Boolean);
      const lines = [
        `Badge: ${scan.ocr_confidence?.script_type ?? "?"} — confidence ${scan.ocr_confidence?.confidence_score ?? "?"}`,
        `Neologisms: ${neologismList.join(", ") || "none"}`,
        "Pre-filled terms:",
      ];
      for (const [term, preference] of Object.entries(scan.prefilled_terms ?? {})) {
        lines.push(`  ${term} → ${preference.preferred_translation}`);
      }
      showResult(lines.join("\n"));
    } catch (error) {
      showResult(`Pre-scan failed: ${error.message}`);
    }
  });

  async function refreshVocabulary() {
    const { userId } = api.requireIdentity();
    const terms = await api.getJson(`/api/v1/vocabulary/${encodeURIComponent(userId)}`);
    vocabList.innerHTML = "";
    for (const [term, preference] of Object.entries(terms ?? {})) {
      const item = document.createElement("li");
      item.textContent = `${term} → ${preference.preferred_translation}`;
      vocabList.append(item);
    }
    const blob = await api.download(`/api/v1/vocabulary/${encodeURIComponent(userId)}/export`);
    exportLink.href = URL.createObjectURL(blob);
    exportLink.download = "terminology.tsv";
    exportLink.hidden = false;
  }

  root.querySelector("#vocab-refresh").addEventListener("click", () => {
    refreshVocabulary().catch((error) => showResult(`Vocabulary refresh failed: ${error.message}`));
  });

  root.querySelector("#vocab-save").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    try {
      await api.postJson(`/api/v1/vocabulary/${encodeURIComponent(userId)}`, {
        german_term: root.querySelector("#vocab-term").value,
        preferred_translation: root.querySelector("#vocab-translation").value,
      });
      await refreshVocabulary();
    } catch (error) {
      showResult(`Save failed: ${error.message}`);
    }
  });

  root.querySelector("#vocab-import-btn").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    try {
      await api.postJson(`/api/v1/vocabulary/${encodeURIComponent(userId)}/import`, {
        tsv_content: root.querySelector("#vocab-import").value,
      });
      await refreshVocabulary();
    } catch (error) {
      showResult(`Import failed: ${error.message}`);
    }
  });
}
