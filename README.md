# 北邮第二课堂活动监控 / BUPT Activity Notifier

一个独立的、**只读**的北邮第二课堂校园活动监控项目。用 Python 获取学生端活动列表，按 **校区 / 是否报名 / 是否签到 / 是否签退** 判断条件，向微信或 QQ 推送新匹配的活动。

> **状态：API 实测通过，自动续期与真实推送待验收。** 2026-10-14 已分别从登录网页和**独立 Python requests** 通过只读接口获取 **19 条活动**，其中 **1 条**符合预设筛选条件。本仓库不包含真实 Token、用户数据或小程序原始代码。

## 已实现

- 自动从有效 JWT 的 `sub` 获取本人用户信息：`GET /api/v1/user/{currentUserId}`
- 自动取得 `college_id`、`class_id`、`grade`、`role_id` 和用户 `digest`，无需手动填写
- 查询学生端校园活动：`GET /api/v1/activity`，固定 `is_group=0`
- 按 `area` 和 `demands` **位标志**筛选
- 首次运行不群发历史通知；其后对新增符合条件活动推送，支持去重和失败重试
- 活动从不符合条件变成符合条件时也会通知
- 可选 [ServerChan](https://sct.ftqq.com/)（微信通知）和 OneBot v11 HTTP（QQ）
- **只调用学校系统的 GET 接口**，不会报名、签到、签退或变更订阅

### 当前默认筛选

```python
area == 1 and (demands & 2) != 0 and (demands & 4) == 0
```

| 字段 | 值 | 含义 |
|---|---|---|
| `area` | `0` | 西土城校区 |
| `area` | `1` | 沙河校区 |
| `area` | `2` | 线上 |
| `area` | `3` | 海南校区 |
| `demands & 1` | 非零 | 需报名 |
| `demands & 2` | 非零 | 需签到 |
| `demands & 4` | 非零 | 需签退 |

未提供 `area` 或 `demands` 的活动**不予匹配**，避免把“未知”误报为“不签退”。

## 快速开始

需要 Python 3.10 及以上。Windows PowerShell：

```powershell
git clone https://github.com/mohualzy/bupt-activity-notifier.git
cd bupt-activity-notifier
python -m pip install -e .
python -m unittest discover -s tests -v
python -m bupt_activity_notifier --demo
```

`--demo` 使用**完全虚构的离线数据**，无需账号。

### 连接真实活动接口

```powershell
Copy-Item .env.example .env
# 在本地编辑 .env，只需填写本人账号的 SECONDCLASS_TOKEN
python -m bupt_activity_notifier --doctor
python -m bupt_activity_notifier --once --dry-run
python -m bupt_activity_notifier --once
# 确认推送配置后才启用：
python -m bupt_activity_notifier --watch
```

有效 Token 可以从自己已经登录的第二课堂网页浏览器存储中取得（`secondclass.tokenv3`）。这是**敏感登录凭证**：只能放入私人的 `.env` 或进程环境变量，绝不要粘贴到公开讨论、提交到 GitHub 或交给陌生工具。网页/小程序 Token 是否互通受服务器账号策略影响，建议先用 `--doctor` 检查。

程序会在每次轮询中重新读取本人用户上下文和 `digest`，所以 **`.env` 不再需要**手动维护六个用户字段。Token 过期后需要本人重新认证；**没有绕过登录或 KYC 的机制**。

### 推送

- 微信：在 `.env` 设置 `SERVERCHAN_SENDKEY`，遵循 ServerChan 官方账户和发送限制。
- QQ：配置自己管理的 OneBot v11 HTTP 服务的 `ONEBOT_URL`、`ONEBOT_ACCESS_TOKEN`，以及 `ONEBOT_USER_ID` 或 `ONEBOT_GROUP_ID`。

`--dry-run` 只打印筛选结果，不推送，也不修改去重状态。**首次正常运行只建立匹配活动基线**；从第二次开始处理新匹配项。状态保存在被 Git 忽略的 `.state/seen.json`。不要未经允许推送到他人的 QQ 群。

> 已实现推送适配器和单元测试，但尚未用真实推送密钥完成端到端发送。Token 过期时会返回明确的认证失败，不会自动重新登录。

## 项目结构

```text
src/bupt_activity_notifier/
  api.py             # 两步只读认证与查询（真实接口已验收）
  filtering.py       # 校区与签到签退位标志
  monitor.py         # 轮询、状态基线、去重、失败重试
  notifications.py   # ServerChan / OneBot v11
  cli.py             # --demo / --doctor / --once / --watch
tests/               # 不使用真实凭证的单元测试
docs/RESEARCH.md     # 逆向依据、实测结果、剩余限制
```

## 免责声明

非官方开源项目；使用的内部 API **未见官方公开稳定性保证**，其结构、认证和访问策略可能改变。请仅使用本人已获授权的学生账号、低频只读访问，并遵守学校系统及第三方平台规则。

新闻通知监控思路参考 [MaplumeX/bupt_notification](https://github.com/MaplumeX/bupt_notification)；本仓库聚焦**学生端活动列表**，与原仓库独立。
