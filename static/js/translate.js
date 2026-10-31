/** Translation lifecycle: start, poll, complete, download, re-run (FR-05/06). */

import { sessionState } from "./state.js";
import { Poller } from "./polling.js";

const poller = new Poller();

export function initTranslate(root, api) {
  root.innerHTML = `
    <h2>5. Translate a document</h2>
    <label for="translate-file">Choose PDF File</label>
    <input id="translate-file" type="file" accept=".pdf" />
    <div class="row">
      <div>
        <label for="translate-target">Target Language</label>
        <select id="translate-target">
          <option>English</option>
          <option>French</option>
          <option>Spanish</option>
        </select>
      </div>
      <div>
        <label for="translate-pages">Pages to translate</label>
        <input id="translate-pages" type="number" min="1" max="2000" value="50" />
      </div>
      <div>
        <label for="translate-philosophy">Philosophy mode</label>
        <input id="translate-philosophy" type="checkbox" />
      </div>
    </div>
    <div class="row">
      <button id="translate-start" class="primary">Start Advanced Translation</button>
      <button id="jobs-refresh">List my jobs</button>
    </div>
    <div id="translate-status" class="result" hidden></div>
    <div id="translate-warning" class="warning" hidden>
      <span id="translate-warning-text"></span>
      <button id="translate-rerun">Re-run translation</button>
    </div>
    <div id="translate-error" class="error" hidden></div>
    <div class="row">
      <button id="translate-download" disabled>Download translated PDF</button>
    </div>
    <div id="translate-downloads"></div>
    <ul id="jobs-list"></ul>
  `;

  const statusBox = root.querySelector("#translate-status");
  const warning = root.querySelector("#translate-warning");
  const errorBox = root.querySelector("#translate-error");
  const downloadButton = root.querySelector("#translate-download");
  const downloadsList = root.querySelector("#translate-downloads");
  const jobsList = root.querySelector("#jobs-list");

  const showStatus = (text) => {
    statusBox.hidden = false;
    statusBox.textContent = text;
  };

  async function start() {
    const { userId } = api.requireIdentity();
    const file = root.querySelector("#translate-file").files[0];
    if (!file) {
      showStatus("Select a PDF first.");
      return;
    }
    const attempt = sessionState.file === file ? sessionState.attempt + 1 : 1;
    const baseBookId = attempt === 1 ? file.name.replace(/\.pdf$/i, "") : sessionState.baseBookId;
    const bookId = attempt === 1 ? baseBookId : `${baseBookId}-r${attempt}`;
    const sessionId = crypto.randomUUID();

    sessionState.file = file;
    sessionState.baseBookId = baseBookId;
    sessionState.bookId = bookId;
    sessionState.sessionId = sessionId;
    sessionState.attempt = attempt;
    sessionState.summary = null;

    warning.hidden = true;
    errorBox.hidden = true;
    downloadButton.disabled = true;
    showStatus(`Submitting batch translation for ${bookId} (session ${sessionId})…`);

    const job = await api.upload("/api/v1/book/translate", file, {
      user_id: userId,
      session_id: sessionId,
      book_id: bookId,
    });
    // Adopt the server-confirmed session id (the backend owns job identity).
    sessionState.sessionId = job.session_id || sessionId;
    showStatus("Batch submitted. Polling progress…");

    poller.start(async () => {
      const progress = await api.getJson(`/api/v1/book/status/${encodeURIComponent(sessionState.sessionId)}`, {
        query: { user_id: userId },
      });
      showStatus(
        `State: ${progress.state} — ${progress.completion_pct.toFixed(1)}% ` +
          `(${progress.translated_pages}/${progress.total_pages} pages)`
      );
      if (progress.is_done) {
        poller.stop();
        if (progress.state === "FAILED") {
          errorBox.hidden = false;
          errorBox.textContent = "Translation failed on Google Cloud. No locally synthesized pages are produced; use Re-run or contact support.";
          return;
        }
        await complete(userId);
      }
    });
  }

  async function complete(userId) {
    const summary = await api.postJson(
      `/api/v1/book/complete/${encodeURIComponent(sessionState.sessionId)}`,
      null,
      { query: { user_id: userId } },
    );
    sessionState.summary = summary;
    downloadButton.disabled = false;
    appendAttemptDownload(sessionState.attempt, sessionState.sessionId);
    if (summary.failed_pages > 0) {
      warning.hidden = false;
      root.querySelector("#translate-warning-text").textContent =
        `${summary.failed_pages} page(s) failed layout-preserved translation. ` +
        "Re-run the translation to retry them (your current output stays downloadable).";
    }
    showStatus(`Completed: ${summary.translated_pages}/${summary.total_pages} pages translated.`);
  }

  function appendAttemptDownload(attempt, sessionId) {
    const link = document.createElement("a");
    link.dataset.session = sessionId;
    link.textContent = `Download attempt ${attempt} output`;
    link.href = "#";
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      const { userId } = api.requireIdentity();
      const blob = await api.download(
        `/api/v1/book/download/${encodeURIComponent(sessionId)}`,
        { query: { user_id: userId } },
      );
      const download = document.createElement("a");
      download.href = URL.createObjectURL(blob);
      download.download = `${sessionId}_translated.pdf`;
      download.click();
      URL.revokeObjectURL(download.href);
    });
    downloadsList.append(link);
  }

  root.querySelector("#translate-start").addEventListener("click", () => {
    start().catch((error) => {
      poller.stop();
      showStatus(`Start failed: ${error.message}`);
    });
  });

  root.querySelector("#translate-rerun").addEventListener("click", () => {
    start().catch((error) => {
      poller.stop();
      showStatus(`Re-run failed: ${error.message}`);
    });
  });

  downloadButton.addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    const blob = await api.download(
      `/api/v1/book/download/${encodeURIComponent(sessionState.sessionId)}`,
      { query: { user_id: userId } },
    );
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${sessionState.bookId}_translated.pdf`;
    link.click();
    URL.revokeObjectURL(link.href);
  });

  root.querySelector("#jobs-refresh").addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    try {
      const jobs = await api.getJson(`/api/v1/book/jobs/${encodeURIComponent(userId)}`);
      jobsList.innerHTML = "";
      for (const job of jobs ?? []) {
        const item = document.createElement("li");
        item.textContent = `${job.book_id} — ${job.status} (${job.translated_pages}/${job.total_pages} pages)`;
        jobsList.append(item);
      }
    } catch (error) {
      jobsList.textContent = `Job list failed: ${error.message}`;
    }
  });
}
