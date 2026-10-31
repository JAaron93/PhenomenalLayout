/** Shared per-session translation state (in-memory only; never persisted). */

export const sessionState = {
  file: null,
  sessionId: null,
  bookId: null,
  baseBookId: null,
  attempt: 1,
  summary: null,
};
