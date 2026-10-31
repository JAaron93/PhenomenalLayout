/** Dual-pane viewer: synchronized German/English text pairs, text-only (FR-07). */

export function initDualpane(root, api) {
  root.innerHTML = `
    <h2>6. Dual-pane viewer</h2>
    <label for="dualpane-session">Session ID</label>
    <input id="dualpane-session" autocomplete="off" />
    <label for="dualpane-file">Source PDF</label>
    <input id="dualpane-file" type="file" accept=".pdf" />
    <div class="row">
      <div>
        <label for="dualpane-page">Page</label>
        <input id="dualpane-page" type="number" min="1" value="1" />
      </div>
      <button id="dualpane-load" class="primary">Load page</button>
    </div>
    <div id="dualpane-content" class="result" hidden></div>
  `;

  const content = root.querySelector("#dualpane-content");

  root.querySelector("#dualpane-load").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    const file = root.querySelector("#dualpane-file").files[0];
    const sessionId = root.querySelector("#dualpane-session").value;
    const pageNumber = root.querySelector("#dualpane-page").value;
    if (!file || !sessionId) {
      content.hidden = false;
      content.textContent = "Provide a session ID and the source PDF.";
      return;
    }
    content.hidden = false;
    content.textContent = "Loading page…";
    try {
      const pair = await api.upload(
        `/api/v1/book/dual-pane/${encodeURIComponent(sessionId)}`,
        file,
        {},
        { query: { user_id: userId, page_number: pageNumber } },
      );
      content.textContent = [
        `Page ${pair.page_number} of ${pair.total_pages_german} (DE) / ${pair.total_pages_english} (EN)`,
        "",
        `— German original —`,
        pair.german_text,
        "",
        `— English translation —`,
        pair.english_text,
      ].join("\n");
    } catch (error) {
      content.textContent = `Dual-pane failed: ${error.message}`;
    }
  });
}
