"use strict";

// Only reads the official site's own localStorage; never accesses cookies.
(() => {
  if (window.top !== window || location.origin !== "https://dekt.bupt.edu.cn") return;
  const STORAGE_KEY = "secondclass.tokenv3";
  const JWT_PATTERN = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
  let acknowledged = "";
  let sending = false;
  let retryAfter = 0;

  function trySync() {
    if (sending || Date.now() < retryAfter) return;
    let candidate = "";
    try {
      candidate = window.localStorage.getItem(STORAGE_KEY) || "";
    } catch (_) {
      return;
    }
    if (!JWT_PATTERN.test(candidate) || candidate.length > 8192 || candidate === acknowledged) return;
    sending = true;
    chrome.runtime.sendMessage({ kind: "sync-candidate", jwt: candidate }, (result) => {
      sending = false;
      if (chrome.runtime.lastError || !result) {
        retryAfter = Date.now() + 60000;
        return;
      }
      if (result.final === true) acknowledged = candidate;
      else retryAfter = Date.now() + 60000;
    });
  }

  window.addEventListener("storage", (event) => {
    if (event.key === STORAGE_KEY) trySync();
  });
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", trySync, { once: true });
  }
  trySync();
  setInterval(trySync, 10000);
})();
