/** Token + User ID identity panel; sessionStorage only (NFR-01). */

const TOKEN_KEY = "pl.token";
const USER_KEY = "pl.userId";
const TOKEN_TYPE_KEY = "pl.tokenType";

export function getStoredIdentity() {
  return {
    token: sessionStorage.getItem(TOKEN_KEY) ?? "",
    userId: sessionStorage.getItem(USER_KEY) ?? "",
    tokenType: sessionStorage.getItem(TOKEN_TYPE_KEY) ?? "bearer",
  };
}

export function initAuth(root) {
  root.innerHTML = `
    <div class="row">
      <div>
        <label for="auth-token-type">Token Type</label>
        <select id="auth-token-type">
          <option value="bearer">Bearer (JWT)</option>
          <option value="api-key">API Key</option>
        </select>
      </div>
      <div>
        <label for="auth-token">API Key or Bearer Token</label>
        <input id="auth-token" type="password" autocomplete="off" />
      </div>
      <div>
        <label for="auth-user">User ID</label>
        <input id="auth-user" autocomplete="off" />
      </div>
      <button id="auth-save" class="primary">Save session</button>
      <button id="auth-clear">Log out</button>
    </div>
    <div id="auth-prompt" class="auth-prompt" hidden></div>
  `;

  const tokenTypeSelect = root.querySelector("#auth-token-type");
  const tokenInput = root.querySelector("#auth-token");
  const userInput = root.querySelector("#auth-user");
  const prompt = root.querySelector("#auth-prompt");

  const stored = getStoredIdentity();
  tokenTypeSelect.value = stored.tokenType;
  tokenInput.value = stored.token;
  userInput.value = stored.userId;

  root.querySelector("#auth-save").addEventListener("click", () => {
    sessionStorage.setItem(TOKEN_KEY, tokenInput.value);
    sessionStorage.setItem(USER_KEY, userInput.value);
    sessionStorage.setItem(TOKEN_TYPE_KEY, tokenTypeSelect.value);
    hidePrompt();
    document.dispatchEvent(new CustomEvent("pl:auth-changed"));
  });

  root.querySelector("#auth-clear").addEventListener("click", () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    sessionStorage.removeItem(TOKEN_TYPE_KEY);
    tokenTypeSelect.value = "bearer";
    tokenInput.value = "";
    userInput.value = "";
    document.dispatchEvent(new CustomEvent("pl:auth-changed"));
  });

  return {
    get token() {
      return tokenInput.value;
    },
    get tokenType() {
      return tokenTypeSelect.value;
    },
    get userId() {
      return userInput.value;
    },
    prompt(message) {
      prompt.textContent = message;
      prompt.hidden = false;
    },
  };
}

function hidePrompt() {
  const prompt = document.getElementById("auth-prompt");
  if (prompt) {
    prompt.hidden = true;
  }
}
