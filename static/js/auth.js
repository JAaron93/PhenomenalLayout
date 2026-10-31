/** Token + User ID identity panel; sessionStorage only (NFR-01). */

const TOKEN_KEY = "pl.token";
const USER_KEY = "pl.userId";

export function getStoredIdentity() {
  return {
    token: sessionStorage.getItem(TOKEN_KEY) ?? "",
    userId: sessionStorage.getItem(USER_KEY) ?? "",
  };
}

export function initAuth(root) {
  root.innerHTML = `
    <div class="row">
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

  const tokenInput = root.querySelector("#auth-token");
  const userInput = root.querySelector("#auth-user");
  const prompt = root.querySelector("#auth-prompt");

  const stored = getStoredIdentity();
  tokenInput.value = stored.token;
  userInput.value = stored.userId;

  root.querySelector("#auth-save").addEventListener("click", () => {
    sessionStorage.setItem(TOKEN_KEY, tokenInput.value);
    sessionStorage.setItem(USER_KEY, userInput.value);
    hidePrompt();
    document.dispatchEvent(new CustomEvent("pl:auth-changed"));
  });

  root.querySelector("#auth-clear").addEventListener("click", () => {
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    tokenInput.value = "";
    userInput.value = "";
    document.dispatchEvent(new CustomEvent("pl:auth-changed"));
  });

  return {
    get token() {
      return tokenInput.value;
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
