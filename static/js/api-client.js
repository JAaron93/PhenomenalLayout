/** Fetch wrapper attaching credentials and normalizing API errors. */

export class ApiError extends Error {
  constructor(status, message, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export function withQuery(path, query = {}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") {
      params.append(key, String(value));
    }
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export function createApiClient({ getToken, getTokenType, getUserId, onAuthRequired }) {
  function authHeaders(extra = {}) {
    const token = getToken();
    if (!token) {
      return { ...extra };
    }
    const type = getTokenType ? getTokenType() : null;
    const isApiKey =
      type === "api-key" ||
      (!type && !token.includes(".") && !token.startsWith("ey"));
    if (isApiKey) {
      return { "X-API-Key": token, ...extra };
    }
    return { Authorization: `Bearer ${token}`, ...extra };
  }

  function requireIdentity() {
    const token = getToken();
    const userId = getUserId();
    if (!token || !userId) {
      onAuthRequired?.(0);
      throw new ApiError(0, "Authentication required: provide a token and User ID.");
    }
    return { token, userId };
  }

  async function handle(response) {
    if (response.status === 401 || response.status === 403) {
      const payload = await safeJson(response);
      onAuthRequired?.(response.status);
      throw new ApiError(response.status, payload.detail ?? "Access denied", payload);
    }
    if (!response.ok) {
      const payload = await safeJson(response);
      throw new ApiError(response.status, payload.detail ?? response.statusText, payload);
    }
    return response;
  }

  async function safeJson(response) {
    try {
      return await response.json();
    } catch {
      return {};
    }
  }

  return {
    requireIdentity,

    async getJson(path, { query } = {}) {
      const response = await fetch(withQuery(path, query), { headers: authHeaders() });
      return (await handle(response)).json();
    },

    async postJson(path, body, { query } = {}) {
      const response = await fetch(withQuery(path, query), {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: body === undefined || body === null ? undefined : JSON.stringify(body),
      });
      return (await handle(response)).json();
    },

    async delete(path, { query } = {}) {
      const response = await fetch(withQuery(path, query), {
        method: "DELETE",
        headers: authHeaders(),
      });
      await handle(response);
      return true;
    },

    async postForm(path, formData) {
      const response = await fetch(path, {
        method: "POST",
        headers: authHeaders(),
        body: formData,
      });
      return (await handle(response)).json();
    },

    async upload(path, file, fields = {}, { query } = {}) {
      const formData = new FormData();
      for (const [key, value] of Object.entries(fields)) {
        formData.append(key, value);
      }
      formData.append("file", file);
      return this.postForm(withQuery(path, query), formData);
    },

    async download(path, { query } = {}) {
      const response = await fetch(withQuery(path, query), { headers: authHeaders() });
      return (await handle(response)).blob();
    },
  };
}
