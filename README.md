# 北邮第二课堂活动监控 / BUPT Activity Notifier

面向北邮学生的**非官方、只读**第二课堂活动提醒器。读取学生端真实活动列表，**只筛选沙河校区**；不论是否报名、签到或签退，有新活动就通过微信或 QQ 提醒。

**当前进度（2026-10-14）：** 校园活动接口已由 Windows 浏览器与独立 Python `requests` 两种方式实测 HTTP 200；当时返回 19 条活动、按**旧版签到规则**有 1 条符合条件；新版已扩大为**所有沙河校区活动**。推送接入代码、本地模拟测试及 **ServerChan → 本人微信端测试消息真实送达** 已验收；Windows 登录自启后台任务已持续运行，并于 16:16 **真实发现一条新活动、成功提交一次微信渠道推送且未重复通知**（该活动的手机实收待本人确认）。**自动登录和多日连续运行尚未验收**。

## 已实现

- 自动读取本人用户上下文及 `digest`，只需有效的本人 Token
- 读取 `GET /api/v1/activity`，无需微信小程序持续运行
- 将带 `Z` / 时区偏移的活动时间转换为**北京时间（UTC+8）**显示；无时区信息的时间不擅自推断
- **仅按校区筛选：`area == 1`（沙河校区）**；`demands` 只用于通知中显示报名、签到和签退规则，不参与筛选
- 首次运行建立基线；从旧筛选条件升级时也会把当前已有的沙河活动纳入基线，保留之前的去重/分渠道回执，避免补发大量历史消息
- 微信 ServerChan 使用分行 Markdown 排版（标题、地点、开始/结束时间、报名、签到、签退和 ID）；QQ OneBot v11 私聊/群聊（需自行配置）
- **分渠道确认与重试**：微信成功、QQ 失败时，重新运行不会再次给微信发送同一条消息
- Windows 任务计划程序登录自启、日志轮换、单实例防重复运行
- `--watch` 每轮重读私有 `.env` 或 Token 文件；到期前 24 小时和已过期时分别向配置的微信/QQ 渠道最多提醒一次
- Docker Compose 部署样例及 CI 构建测试
- 不报名、不签到、不签退、不修改账号

## 快速开始

Python 3.10+：

```powershell
cd D:\Projects\bupt-activity-notifier
python -m pip install -e .
python -m unittest discover -s tests -q
python -m bupt_activity_notifier --demo
```

`--demo` 完全离线，不需要账号，不会向学校请求数据。

### 接入真实接口

```powershell
Copy-Item .env.example .env
# 只在本地 .env 配置 SECONDCLASS_TOKEN 或 SECONDCLASS_TOKEN_FILE
python -m bupt_activity_notifier --doctor
python -m bupt_activity_notifier --once --dry-run
```

Token 来自**你本人有权使用的已登录第二课堂网页或小程序**。请勿把它发送给他人、上传仓库或写入日志。

`--doctor` 只显示接口状态、活动数量和字段名；`--dry-run` 只显示匹配活动，不发送，也不写入去重状态。

设置好推送渠道后：

```powershell
python -m bupt_activity_notifier --test-push
python -m bupt_activity_notifier --once
python -m bupt_activity_notifier --watch
```

`--test-push` **会真的发送一条明确标为“测试”的消息**；只在你配置了本人可控的推送渠道后执行。第一次 `--once` 或 `--watch` 仅保存当前匹配活动作为基线，不会轰炸历史消息；之后新增匹配才通知。

Windows 登录自启（需先运行一次 `--once` 初始化基线）：

```powershell
pwsh -NoProfile -File .\scripts\install_windows_task.ps1
Get-ScheduledTask -TaskName BUPT-SecondClass-Activity-Watcher
Get-Content .\logs\watch.log -Tail 20
```

计划任务以**当前登录用户**运行，电脑关机、睡眠或用户退出登录时不会继续轮询；参见 [部署指南](docs/DEPLOYMENT.md) 了解暂停、恢复和卸载。

## 关键字段

| 字段 | 用法 |
|---|---|
| `area == 1` | 沙河校区；其他值详见[研究记录](docs/RESEARCH.md) |
| `demands & 1` | 需报名 |
| `demands & 2` | 需签到 |
| `demands & 4` | 需签退 |

`demands` 字段只用于**展示活动要求**：缺失时明确写“未知”，不会误报为无需签退，也不会阻止沙河活动推送。

## 通知配置与 Token 轮换

- **微信**：在 `.env` 中设置 `SERVERCHAN_SENDKEY`，需先自行开通 [ServerChan Turbo](https://sct.ftqq.com/sendkey/)。
- **QQ**：配置自己管理的 OneBot v11 HTTP 服务，`ONEBOT_URL`、`ONEBOT_ACCESS_TOKEN`、`ONEBOT_USER_ID` 或 `ONEBOT_GROUP_ID`。
- **Token 更新**：运行中的 `--watch` 会每轮重新读取 `.env`；直接替换 `SECONDCLASS_TOKEN` 即可，无需重启。也可设置 `SECONDCLASS_TOKEN_FILE=secrets/token.txt`，优先从该被 Git 忽略的私有文件读取。
- **失效处理**：当前**没有自动模拟登录或绕过验证码**的功能。Token 过期时停止有效数据查询，等本人合法重新认证并更新凭证。已核读网页登录模块及 58 个按需加载脚本，尚未确认可供学生使用的自动刷新协议。进一步实测：本人 Edge 复用北邮 SSO 会话可免输密码取得 CAS Ticket，但第二课堂回调页面最终退回登录；公开学生社区指南还将网页登录视为**管理端**、微信小程序视为**普通学生端**。**尚未证明 SSO 生成的 JWT 可替代当前学生端 Token**；详见 [Token 自动续期可行性调研](docs/AUTH_RENEWAL_RESEARCH.md)。

ServerChan Turbo 免费额度较小（官方文档说明每天 5 条），建议合理控制通知频率。单条消息只有在第三方接口确认成功后才记录为送达；极端情况下，如果第三方已发送成功但本机在写入状态前突然断电，仍有重发可能。

项目工作状态默认位于被 Git 忽略的 `.state/seen.json`（兼容旧版 v0.2 状态）；Token 过期提醒回执单独保存在 `.state/auth_notices.json`，只记录到期时间及成功渠道，不存放 JWT。

## Edge 正常登录后自动更新 Token（一次性扩展安装）

可选：在 **Microsoft Edge** 通过北邮第二课堂官网登录成功后，浏览器扩展自动把新 JWT 交给**本机 Native Messaging** 主机。只有同一账号、相同登录上下文、过期时间延长且真实学生端活动查询 HTTP 200 的凭证才会原子替换项目私有 .env 中的 SECONDCLASS_TOKEN（配置 Token 文件时更新对应私有文件）。原来的 5 分钟监控随后自动读取新凭证，无需重启，也不会清空活动去重记录。

- 一次性部署：安装脚本 `scripts/install_edge_token_sync.ps1` 只注册本机消息主机；还需要本人在 Edge 的 `edge://extensions` 中开启开发人员模式，使用“加载解压缩的扩展”，选择本仓库的 `edge_token_sync` 目录。扩展 ID 应为 `mcohcjkicfoblidoolgbpladhehllpbb`。
- 扩展仅在 `https://dekt.bupt.edu.cn/*` 页面生效，不读取浏览器 Cookie、密码、其他网站，也不开放本地 HTTP 端口。不会自动登录、不解决验证码或微信小程序端续期；**只同步已经由正常 Edge 网页合法签发的新 Token**。
- 具体安装、验证、安全边界及卸载方式见 [Edge 本机同步指南](docs/EDGE_TOKEN_SYNC.md)。扩展尚未在本人的 Edge 中人工启用前，不得声称真实端到端同步已验收。

## Docker 部署

仓库包含 `Dockerfile` 和 `compose.yaml`，支持**非 root 容器、只读根文件系统、独立持久卷、只读密钥文件**。见 [部署指南](docs/DEPLOYMENT.md)。Docker 不负责自动获取你的登录凭证。

## 项目文件

```text
src/bupt_activity_notifier/
  api.py             # 用户上下文、JWT 有效期、只读活动 API
  filtering.py       # 只按沙河校区筛选，格式化报名/签到/签退信息
  monitor.py         # 持久化去重、分渠道回执和失败重试
  notifications.py   # 微信 ServerChan / QQ OneBot
  auth_notice.py     # Token 到期前 / 到期后限次提醒
  cli.py             # demo / doctor / test-push / once / watch
scripts/
  windows_watch.py   # Windows 后台单实例启动与有限日志
  install_windows_task.ps1  # 当前用户的登录自启任务
tests/               # 合成数据单元测试，不包含真实 Token
docs/RESEARCH.md     # 已实测证据与待解决的问题
docs/DEPLOYMENT.md   # 本地与 Docker 使用说明
```

## 安全边界

这是独立实现，**没有**提交解密过的小程序源文件、抓包、个人资料或真实认证凭证。服务端仅使用第二课堂网站的只读 GET 请求；通知使用使用者自己配置的第三方推送账户。请遵守学校及第三方平台的访问规则，避免高频查询；内部 API 可能变更，不保证官方支持。

新闻通知项目的思路参考 [MaplumeX/bupt_notification](https://github.com/MaplumeX/bupt_notification)；本项目聚焦**学生端活动列表**。
