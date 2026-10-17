"use strict";

const NATIVE_HOST = "com.mohualzy.bupt_token_sync";
const WEBSITE = "https://dekt.bupt.edu.cn/";
const FINAL = new Set([
  "updated", "already_current", "not_newer", "wrong_account",
  "different_context", "expired_candidate", "invalid_candidate",
  "missing_current", "bad_config", "verification_failed"
]);

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message?.kind !== "sync-candidate") return false;
  if (sender.frameId !== 0 || typeof sender.url !== "string" ||
      !sender.url.startsWith(WEBSITE) || sender.id !== chrome.runtime.id) {
    respond({ final: true });
    return false;
  }
  const jwt = message.jwt;
  if (typeof jwt !== "string" || jwt.length > 8192 ||
      !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(jwt)) {
    respond({ final: true });
    return false;
  }

  // Only the Edge-native-messaging pipe receives this JWT.
  // Never save it to browser storage or emit it to logs.
  chrome.runtime.sendNativeMessage(NATIVE_HOST, { kind: "sync", jwt }, (response) => {
    const error = chrome.runtime.lastError;
    const status = error ? "native_host_unavailable"
      : typeof response?.status === "string" ? response.status : "native_host_error";
    const safeStatus = /^[a-z_]{2,40}$/.test(status) ? status : "native_host_error";
    chrome.storage.local.set({ lastSyncStatus: safeStatus, lastSyncAt: Date.now() });
    const badge = safeStatus === "updated" || safeStatus === "already_current" ? "OK" : "!";
    chrome.action.setBadgeText({ text: badge });
    chrome.action.setBadgeBackgroundColor({color: badge === "OK" ? "#176e4c" : "#a45c16"});
    respond({ final: FINAL.has(safeStatus), status: safeStatus });
  });
  return true;
});
