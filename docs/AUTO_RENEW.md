# 自动重登与 Token 续期（Windows v0.5，可选）

状态（2026-10-14）：**实现和离线验收完成，真实账号的自动重登尚未验收，默认关闭。**现有独立只读 watcher 和微信推送继续正常运行。

## 技术路线与来源

参考你最早提供的开源项目 [MaplumeX/bupt_notification](https://github.com/MaplumeX/bupt_notification) 的 `bupt_notification/web_login.py`。它使用 Playwright 填写第二课堂网页账号密码，等待 `localStorage["secondclass.tokenv3"]` 中的新 JWT，然后后续通过轻量 HTTP API 访问。**这是重新登录，不是 JWT refresh_token 接口，也不是学校 SSO 免密续期。**

适配至本项目的差异：

- 不复制其 `--disable-blink-features=AutomationControlled`、UA 伪装等绕过自动化检测行为。登录需正常完成学校要求的交互，遇验证码、MFA、风控时停下并由本人处理。
- **不保存明文密码到项目的 `.env`、`state.json`、工作日志或任何 Git 文件。**账号密码只通过本机交互式终端录入到 Windows Credential Manager 的当前用户通用凭据 `BUPT-Activity-Notifier:Login`。
- 新 JWT 通过 `BUPT-Activity-Notifier:RenewedToken` 保存在当前用户 Windows Credential Manager；受 Windows 登录用户的保护，但**不能防护该用户权限下的恶意进程**。
- 只有 JWT `sub` 与原账号相同、到期时间比旧 JWT 充分延长（至少 1 小时）、距到期不少于 24 小时，并且新 JWT 真实通过 **`GET /api/v1/user/{sub}` 与 `GET /api/v1/activity`** 后，才会切换活动监控。
- 失败不更改现有已知有效的 Token，保留原来的到期前微信提醒；自动重登两次尝试至少相隔 12 小时。无需重设去重状态，也不会重复推送历史消息。
- 登录凭据会在每次自动登录时送往**第二课堂官网的正常网页登录表单**，不传给 Telegram、ServerChan 或其他代理。此功能仅适合使用者本人拥有的账户。

## 独立实验分支：一次可视化登录验收（推荐先完成）

实验代码存放在 `D:\\Projects\\bupt-activity-notifier-lab`，正式活动监控继续使用 `D:\\Projects\\bupt-activity-notifier` 的稳定 `main`，互不修改源码。已在同一 Windows 用户的 Credential Manager 中保存官网网页登录凭据的使用者，不必重复录入密码。

**在你本人直接打开的、非远程重定向的 PowerShell 窗口**执行一行：

```powershell
pwsh -NoProfile -File 'D:\Projects\bupt-activity-notifier-lab\scripts\run_visible_renewal_trial.ps1'
```

此脚本临时从正式项目的私有 `.env` **内存加载现有 Token**，实际使用独立实验代码启动 **可见的正常 Edge**。遇网站官方验证码/人工验证时在浏览器里自行完成，不自动识别或绕过。只记录脱敏的失败阶段码；不显示/保存密码、响应正文、Cookie、Ticket 或 JWT。即使成功，**也只是将新 JWT 写入该 Windows 用户的凭据管理器，自动续期仍保持关闭**，不修改正式仓库、原 `.env`、定时任务与活动去重账本。

失败阶段代码：`verification_required`（网站要求交互验证）、`login_rejected`（网页登录拒绝）、`login_not_completed`（登录后未获得新 JWT）、`wrong_student`（JWT 账号不符）、`not_renewed`（JWT 未延长有效期）、`student_api_rejected`（新 JWT 不能访问学生端活动 API）、`browser_error`（浏览器层异常）。**成功须显示 student token passed read-only API validation**；任何单纯网页“登录成功”提示都不够。

## 本机部署（需在用户本人的交互式 PowerShell 中）

保持本地已有登录 Token 与微信 SendKey，不要删除 `.env`、`.state/seen.json`：

```powershell
cd D:\Projects\bupt-activity-notifier-lab
python -m pip install playwright
$env:PYTHONPATH = "$PWD\src"
```

**第一步：** 在你的电脑终端执行，自己输入第二课堂官网登录账号和密码；密码不会回显，助手及终端命令历史不会看到值。

```powershell
python -m bupt_activity_notifier --setup-auto-renew
```

这一步只写入当前 Windows 用户的凭据管理器，**不启用**自动重登。

**第二步：** 使用上文的 `run_visible_renewal_trial.ps1` 在本人交互式终端进行一次人工可见的 Playwright 登录验收。已保存网页登录凭据的用户可以直接跳过第一步。实验进程不收集新的密码输入，也不读取 Edge 现有 Cookie。

**第三步：** 只有第二步经同账户 JWT、延长有效期和学生端只读接口完整验证通过后，才能继续研究无头模式在学校认证规则下能否稳定自动更新。**当前阶段不建议运行 `--enable-auto-renew`，且该实验分支并未合入正式 `main`**。已有稳定监控继续靠原 Token 和微信过期提醒运行，不受实验影响。

## 立即停止、删除与恢复

```powershell
# 只停止自动续期；原来 .env 中的手动 Token 和活动去重状态保持不变
python -m bupt_activity_notifier --disable-auto-renew

# 停止自动续期，并从 Windows 凭据管理器删除保存的密码与续期 JWT
python -m bupt_activity_notifier --forget-auto-renew
```

如果原始 `SECONDCLASS_TOKEN` 已过期，关闭自动续期后仍需要手动替换本地旧 Token。

## 隐私与失败边界

- **不要**把账号密码、JWT、CAS Ticket、验证码发到聊天、README、Issue 或 GitHub。
- 不读取用户现有 Edge 登录配置文件，也不访问浏览器的现成登录 Cookie；每次用独立的 Playwright 浏览器环境请求学校官方登录页。
- 不绕过验证码、MFA、校园认证或者反自动化限制；若学校阻止自动化登录，以手动认证 + 微信过期提醒为后备，不反复冲击认证服务。
- 当前学生账号的真实自动网页登录、后台多日自动续期和验证码挑战处理都**尚未通过真实验收**。这是一个带严格安全门、可以由本人自愿启用的适配，不是已经完成的免密承诺。
- 一旦学校官方明确禁止此类自动登录，请不要启用或立即关闭。
