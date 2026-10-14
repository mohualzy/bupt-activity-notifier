# 北邮第二课堂活动监控 / BUPT Activity Notifier

面向北邮学生的**非官方、只读**第二课堂活动提醒器。读取学生端真实活动列表，筛选**沙河校区、需签到、不签退**的活动，并在有新匹配时通过微信或 QQ 提醒。

**当前进度（2026-10-14）：** 校园活动接口已由 Windows 浏览器与独立 Python `requests` 两种方式实测 HTTP 200；当时返回 19 条活动，1 条符合筛选条件。推送接入代码、本地模拟测试及 **ServerChan → 本人微信端真实送达** 已验收；**长期自动登录及持续运行尚未验收**。

## 已实现

- 自动读取本人用户上下文及 `digest`，只需有效的本人 Token
- 读取 `GET /api/v1/activity`，无需微信小程序持续运行
- 位标志筛选：`area == 1 and (demands & 2) != 0 and (demands & 4) == 0`
- 首次运行建立基线；新增匹配活动推送，避免大量历史消息
- 微信 ServerChan、QQ OneBot v11 私聊/群聊（需自行配置）
- **分渠道确认与重试**：微信成功、QQ 失败时，重新运行不会再次给微信发送同一条消息
- Token 可从私有文件每轮重新加载；失效提示与过期前 24 小时提醒
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

## 关键字段

| 字段 | 用法 |
|---|---|
| `area == 1` | 沙河校区；其他值详见[研究记录](docs/RESEARCH.md) |
| `demands & 1` | 需报名 |
| `demands & 2` | 需签到 |
| `demands & 4` | 需签退 |

若字段缺失，不会把“未知”误报为“免签退”。

## 通知配置与 Token 轮换

- **微信**：在 `.env` 中设置 `SERVERCHAN_SENDKEY`，需先自行开通 [ServerChan Turbo](https://sct.ftqq.com/sendkey/)。
- **QQ**：配置自己管理的 OneBot v11 HTTP 服务，`ONEBOT_URL`、`ONEBOT_ACCESS_TOKEN`、`ONEBOT_USER_ID` 或 `ONEBOT_GROUP_ID`。
- **Token 文件**：可将 `SECONDCLASS_TOKEN_FILE=secrets/token.txt` 配在 `.env`，然后把有效 Token 放入这个**被 Git 忽略**的文件。运行中的 `--watch` 每轮重新读取该文件，更新 Token 无需重启程序。
- **失效处理**：当前**没有自动模拟登录或绕过验证码**的功能。Token 过期时停止有效数据查询，等本人合法重新认证并更新凭证。

ServerChan Turbo 免费额度较小（官方文档说明每天 5 条），建议合理控制通知频率。单条消息只有在第三方接口确认成功后才记录为送达；极端情况下，如果第三方已发送成功但本机在写入状态前突然断电，仍有重发可能。

项目工作状态默认位于被 Git 忽略的 `.state/seen.json`（v0.3 兼容旧版 v0.2 状态）。

## Docker 部署

仓库包含 `Dockerfile` 和 `compose.yaml`，支持**非 root 容器、只读根文件系统、独立持久卷、只读密钥文件**。见 [部署指南](docs/DEPLOYMENT.md)。Docker 不负责自动获取你的登录凭证。

## 项目文件

```text
src/bupt_activity_notifier/
  api.py             # 用户上下文、JWT 有效期、只读活动 API
  filtering.py       # 沙河 / 签到 / 签退精确筛选
  monitor.py         # 持久化去重、分渠道回执和失败重试
  notifications.py   # 微信 ServerChan / QQ OneBot
  cli.py             # demo / doctor / test-push / once / watch
tests/               # 合成数据单元测试，不包含真实 Token
docs/RESEARCH.md     # 已实测证据与待解决的问题
docs/DEPLOYMENT.md   # 本地与 Docker 使用说明
```

## 安全边界

这是独立实现，**没有**提交解密过的小程序源文件、抓包、个人资料或真实认证凭证。服务端仅使用第二课堂网站的只读 GET 请求；通知使用使用者自己配置的第三方推送账户。请遵守学校及第三方平台的访问规则，避免高频查询；内部 API 可能变更，不保证官方支持。

新闻通知项目的思路参考 [MaplumeX/bupt_notification](https://github.com/MaplumeX/bupt_notification)；本项目聚焦**学生端活动列表**。
