# 部署与运行（v0.3）

本项目**不会自动获取或续期微信/学校登录凭证**，且默认不向任何第三方发送通知。使用者需要自己配置 Token 和推送渠道。建议先完成本机只读验收，再考虑全天运行。

## Windows / PowerShell（推荐先用）

在 `D:\Projects\bupt-activity-notifier`：

```powershell
python -m pip install -e .
Copy-Item .env.example .env
```

编辑私有的 `.env`，选择一种认证方式：

1. `SECONDCLASS_TOKEN=你的有效JWT` —— 最简单，但轮换需要重启进程。
2. `SECONDCLASS_TOKEN_FILE=secrets/token.txt` —— 推荐长期轮询时使用。先创建 `secrets` 目录，在 `token.txt` 保存**唯一的一行**有效 JWT。

第二种方式每个轮询周期都会重新读取文件，因此换 Token 不需要重启本地 watcher。敏感文件已经被 `.gitignore` 忽略，不会随 Git 提交。

```powershell
python -m bupt_activity_notifier --doctor
python -m bupt_activity_notifier --once --dry-run
```

这两步只对学校 API 发起 GET 请求，不会触发报名/签到/第三方推送。

设置推送方式后，先用 `python -m bupt_activity_notifier --test-push` 向**自己的**通知渠道发送一条明确的测试消息。确认收到后，再运行：

```powershell
python -m bupt_activity_notifier --watch
```

退出按 Ctrl+C。默认 300 秒轮询一次，调整 `.env` 中的 `POLL_SECONDS`；程序最低强制 60 秒，建议 5 分钟或更低频，尊重学校系统负载。

## Docker Compose（Linux / Docker Desktop）

Docker Linux 引擎、Compose 需要处于可用状态。本项目尚未在本机 Docker Desktop 上运行，GitHub Actions 会自动构建并执行离线样例。

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force secrets | Out-Null
notepad secrets/token.txt
# 粘贴你自己的有效 JWT，保存并退出记事本。
docker compose build
docker compose up -d
docker compose logs --tail=30 notifier
```

`compose.yaml` 配置了：

- 单独的 `activity_state` 命名卷保存 `/data/seen.json`；
- 本地 `secrets/token.txt` 只读挂载为 `/run/secrets/secondclass_token`；
- 非 root 用户运行、容器根目录只读、临时目录为 tmpfs；
- `restart: unless-stopped`，容器重启后保留去重信息。

**换 Token：** 本地替换 `secrets/token.txt` 的内容后，可用 `docker compose up -d --force-recreate` 重新挂载新密钥；不建议依赖“文件替换”会自动更新既有 bind mount。

**暂停：** `docker compose stop`。如需保留活动去重历史，**不要**执行 `docker compose down -v`（这会删除命名卷）。

## 推送

**微信 ServerChan**：访问官方 [SendKey 页面](https://sct.ftqq.com/sendkey/)，自行获取 `SCT...` 格式的密钥，放入本地 `.env` 的 `SERVERCHAN_SENDKEY`。ServerChan Turbo 免费计划按官方说明每日最多 5 条，若匹配新活动很多可能触发额度限制；失败活动会在后续轮询尝试再次发送。

**QQ OneBot v11**：需要自己部署并管理符合 OneBot v11 协议的服务。私聊 `ONEBOT_USER_ID`、群聊 `ONEBOT_GROUP_ID` 可同时配置。非本地 HTTP 禁用，远程端点必须使用 HTTPS；不应开放未鉴权的机器人接口到公网。

程序将不同通知渠道作为独立收件对象：一个渠道确认成功后，即使另一个渠道失败，前者的成功回执也会写入本地状态文件，不会因另一渠道重试而再次发送。对进程突然退出/断电的极短窗口不保证严格一次。

## 认证失败和状态

- `--doctor` 显示接口活动数量及字段结构，不输出身份或 Token。
- JWT 在客户端检测为过期后不再向学校请求接口；`--watch` 提示更换有效 Token，随后继续轮询 Token 文件。
- 距 JWT 过期不足 24 小时会输出一次提醒（当前是**终端提示**，并不会主动发送微信提醒）。
- `.state/seen.json` 是本地去重状态。升级到 v0.3 后会在第一次写入时自动使用新版格式；旧版 `seen_ids` 可读。
- 配置、推送与账号文件均不得提交 GitHub。请使用私有 Token，低频只读访问，不尝试绕过学校的验证/身份限制。

## 尚未完成

真实 ServerChan/OneBot 推送密钥联调、自动重新登录的合法实现、Docker Desktop 本机部署/长期稳定性实测仍待完成。以上说明不应被理解为这三项已验收。
