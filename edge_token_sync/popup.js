"use strict";

const TEXT = {
  updated: "新 Token 已验证，并已更新本机监控。",
  already_current: "本机已使用这个 Token，无需更新。",
  not_newer: "浏览器 Token 不是更新版本，未覆盖本机凭证。",
  wrong_account: "浏览器登录的账号与监控账号不同，拒绝覆盖。",
  different_context: "网页登录场景发生变化，拒绝覆盖。",
  expired_candidate: "浏览器 Token 已失效或即将过期。",
  invalid_candidate: "浏览器 Token 格式异常。",
  missing_current: "本地原 Token 未配置或不可验证。",
  bad_config: "本机 Token 配置需要检查。",
  verification_failed: "新 Token 无法通过学生端 API 验证，未覆盖。",
  native_host_unavailable: "本机连接未启用，请检查扩展安装步骤。",
  native_host_error: "本机通信发生错误，Token 未覆盖。",
  busy: "本机正在处理其他 Token 同步，稍后会重试。"
};
chrome.storage.local.get(["lastSyncStatus", "lastSyncAt"], (state) => {
  document.getElementById("result").textContent =
    TEXT[state.lastSyncStatus] || "等待你在 Edge 登录第二课堂。";
  document.getElementById("time").textContent = state.lastSyncAt
    ? "最近检查：" + new Date(state.lastSyncAt).toLocaleString("zh-CN")
    : "";
});
