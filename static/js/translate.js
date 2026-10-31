/** Translation lifecycle: start, poll, complete, download, re-run, resume (FR-05/06). */

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
          <option value="en-US">English</option>
          <option value="fr">French</option>
          <option value="es">Spanish</option>
        </select>
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
  const startButton = root.querySelector("#translate-start");
  const rerunButton = root.querySelector("#translate-rerun");
  const downloadButton = root.querySelector("#translate-download");
  const downloadsList = root.querySelector("#translate-downloads");
  const jobsList = root.querySelector("#jobs-list");

  const showStatus = (text) => {
    statusBox.hidden = false;
    statusBox.textContent = text;
  };

  function setRunningState(isRunning) {
    sessionState.running = isRunning;
    startButton.disabled = isRunning;
    rerunButton.disabled = isRunning;
  }

  function startPolling(userId, targetSessionId, targetBookId) {
    setRunningState(true);
    showStatus("Batch submitted. Polling progress…");

    poller.start(
      async () => {
        if (sessionState.sessionId !== targetSessionId) {
          poller.stop();
          return;
        }
        const progress = await api.getJson(
          `/api/v1/book/status/${encodeURIComponent(targetSessionId)}`,
          { query: { user_id: userId } }
        );
        if (sessionState.sessionId !== targetSessionId) {
          poller.stop();
          return;
        }
        showStatus(
          `State: ${progress.state} — ${progress.completion_pct.toFixed(1)}% ` +
            `(${progress.translated_pages}/${progress.total_pages} pages)`
        );
        if (progress.is_done) {
          poller.stop();
          setRunningState(false);
          if (progress.state === "FAILED") {
            errorBox.hidden = false;
            errorBox.textContent =
              "Translation failed on Google Cloud. No locally synthesized pages are produced; use Re-run or contact support.";
            return;
          }
          await complete(userId, targetSessionId, targetBookId);
        }
      },
      1000,
      (error) => {
        setRunningState(false);
        errorBox.hidden = false;
        errorBox.textContent = `Progress check failed: ${error.message}. You can reconnect using 'List my jobs'.`;
      }
    );
  }

  async function start() {
    if (sessionState.running) {
      showStatus("A translation job is already in progress.");
      return;
    }
    const { userId } = api.requireIdentity();
    const file = root.querySelector("#translate-file").files[0];
    if (!file) {
      showStatus("Select a PDF first.");
      return;
    }
    const targetLang = root.querySelector("#translate-target")?.value || "en-US";

    let attempt = 1;
    if (sessionState.fileName === file.name && sessionState.baseBookId) {
      attempt = sessionState.attempt;
    }
    const baseBookId =
      sessionState.fileName === file.name && sessionState.baseBookId
        ? sessionState.baseBookId
        : file.name.replace(/\.pdf$/i, "");
    const bookId = attempt === 1 ? baseBookId : `${baseBookId}-r${attempt}`;
    const sessionId = crypto.randomUUID();

    sessionState.file = file;
    sessionState.fileName = file.name;
    sessionState.baseBookId = baseBookId;
    sessionState.bookId = bookId;
    sessionState.sessionId = sessionId;
    sessionState.attempt = attempt;
    sessionState.summary = null;

    warning.hidden = true;
    errorBox.hidden = true;
    downloadButton.disabled = true;
    setRunningState(true);
    showStatus(`Submitting batch translation for ${bookId} (session ${sessionId})…`);

    try {
      const job = await api.upload("/api/v1/book/translate", file, {
        user_id: userId,
        session_id: sessionId,
        book_id: bookId,
        target_lang: targetLang,
      });
      // Adopt the server-confirmed session id (the backend owns job identity).
      const confirmedSessionId = job.session_id || sessionId;
      sessionState.sessionId = confirmedSessionId;

      startPolling(userId, confirmedSessionId, bookId);
    } catch (error) {
      setRunningState(false);
      throw error;
    }
  }

  async function complete(userId, targetSessionId, targetBookId) {
    const activeSessionId = targetSessionId || sessionState.sessionId;
    const activeBookId = targetBookId || sessionState.bookId || "book";
    const summary = await api.postJson(
      `/api/v1/book/complete/${encodeURIComponent(activeSessionId)}`,
      null,
      { query: { user_id: userId } }
    );
    sessionState.summary = summary;
    downloadButton.disabled = false;
    appendAttemptDownload(sessionState.attempt, activeSessionId, activeBookId);
    if (summary.failed_pages > 0) {
      warning.hidden = false;
      root.querySelector("#translate-warning-text").textContent =
        `${summary.failed_pages} page(s) failed layout-preserved translation. ` +
        "Re-run the translation to retry them (your current output stays downloadable).";
    }
    showStatus(
      `Completed: ${summary.translated_pages}/${summary.total_pages} pages translated.`
    );
  }

  function appendAttemptDownload(attempt, sessionId, bookId) {
    const existing = downloadsList.querySelector(`a[data-session="${sessionId}"]`);
    if (existing) {
      return;
    }
    const link = document.createElement("a");
    link.dataset.session = sessionId;
    link.textContent = `Download attempt ${attempt} output`;
    link.href = "#";
    link.addEventListener("click", async (event) => {
      event.preventDefault();
      const { userId } = api.requireIdentity();
      const blob = await api.download(
        `/api/v1/book/download/${encodeURIComponent(sessionId)}`,
        { query: { user_id: userId } }
      );
      const download = document.createElement("a");
      download.href = URL.createObjectURL(blob);
      download.download = `${bookId || sessionId}_translated.pdf`;
      download.click();
      URL.revokeObjectURL(download.href);
    });
    downloadsList.append(link);
  }

  async function resume(sessionId, bookId) {
    if (sessionState.running) {
      poller.stop();
      setRunningState(false);
    }
    const { userId } = api.requireIdentity();
    warning.hidden = true;
    errorBox.hidden = true;
    showStatus(`Reconnecting to job ${bookId || sessionId}…`);

    try {
      const state = await api.getJson(
        `/api/v1/book/resume/${encodeURIComponent(sessionId)}`,
        { query: { user_id: userId } }
      );
      const activeSessionId = state.session_id || sessionId;
      const activeBookId = state.book_id || bookId || "book";

      sessionState.sessionId = activeSessionId;
      sessionState.bookId = activeBookId;
      sessionState.baseBookId = activeBookId.replace(/-r\d+$/, "");

      showStatus(
        `Resumed ${activeBookId}: State: ${state.status} (${state.translated_pages}/${state.total_pages} pages)`
      );

      if (state.status === "SUCCEEDED") {
        await complete(userId, activeSessionId, activeBookId);
      } else if (state.status === "FAILED") {
        setRunningState(false);
        errorBox.hidden = false;
        errorBox.textContent =
          "Translation failed on Google Cloud. No locally synthesized pages are produced; use Re-run or contact support.";
      } else {
        startPolling(userId, activeSessionId, activeBookId);
      }
    } catch (err) {
      setRunningState(false);
      showStatus(`Resume failed: ${err.message}`);
    }
  }

  root.querySelector("#translate-start").addEventListener("click", () => {
    sessionState.attempt = 1;
    start().catch((error) => {
      poller.stop();
      setRunningState(false);
      showStatus(`Start failed: ${error.message}`);
    });
  });

  root.querySelector("#translate-rerun").addEventListener("click", () => {
    sessionState.attempt = (sessionState.attempt || 1) + 1;
    start().catch((error) => {
      poller.stop();
      setRunningState(false);
      showStatus(`Re-run failed: ${error.message}`);
    });
  });

  downloadButton.addEventListener("click", async () => {
    const { userId } = api.requireIdentity();
    const blob = await api.download(
      `/api/v1/book/download/${encodeURIComponent(sessionState.sessionId)}`,
      { query: { user_id: userId } }
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
      const jobs = await api.getJson(
        `/api/v1/book/jobs/${encodeURIComponent(userId)}`
      );
      jobsList.innerHTML = "";
      if (!jobs || jobs.length === 0) {
        jobsList.innerHTML = "<li>No active jobs found.</li>";
        return;
      }
      for (const job of jobs) {
        const item = document.createElement("li");
        const label = document.createElement("span");
        label.textContent = `${job.book_id} — ${job.status} (${job.translated_pages}/${job.total_pages} pages) `;
        item.append(label);

        const resumeBtn = document.createElement("button");
        resumeBtn.textContent = "Resume";
        resumeBtn.dataset.session = job.session_id;
        resumeBtn.className = "resume-job-btn";
        resumeBtn.addEventListener("click", () => {
          resume(job.session_id, job.book_id);
        });
        item.append(resumeBtn);
        jobsList.append(item);
      }
    } catch (error) {
      jobsList.textContent = `Job list failed: ${error.message}`;
    }
  });
}
