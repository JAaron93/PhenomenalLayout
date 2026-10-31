/** SPA entry: wires the auth panel, API client, and feature modules. */

import { initAuth } from "./auth.js";
import { createApiClient } from "./api-client.js";
import { initCostEstimator } from "./cost-estimator.js";
import { initOnboarding } from "./onboarding.js";
import { initByok } from "./byok.js";
import { initPrescan } from "./prescan.js";
import { initTranslate } from "./translate.js";
import { initDualpane } from "./dualpane.js";

const auth = initAuth(document.getElementById("auth-panel"));

const api = createApiClient({
  getToken: () => auth.token,
  getUserId: () => auth.userId,
  onAuthRequired: (status) => {
    auth.prompt(
      status === 0
        ? "Authentication required: enter your API key or bearer token and User ID, then save."
        : `Access rejected (HTTP ${status}). Check your token and User ID, then save again.`,
    );
  },
});

initCostEstimator(document.getElementById("cost-estimator"), api);
initOnboarding(document.getElementById("onboarding"), api);
initByok(document.getElementById("byok"), api);
initPrescan(document.getElementById("prescan"), api);
initTranslate(document.getElementById("translate"), api);
initDualpane(document.getElementById("dualpane"), api);
