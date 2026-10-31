/** Polling primitive with mandatory deactivation (NFR-03). */

export class Poller {
  #timer = null;

  start(fn, intervalMs = 1000, onError = null) {
    this.stop();
    this.#timer = setInterval(() => {
      Promise.resolve()
        .then(fn)
        .catch((err) => {
          this.stop();
          if (onError) {
            onError(err);
          }
        });
    }, intervalMs);
  }

  stop() {
    if (this.#timer !== null) {
      clearInterval(this.#timer);
      this.#timer = null;
    }
  }

  get active() {
    return this.#timer !== null;
  }
}
