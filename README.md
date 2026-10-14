# 北邮第二课堂活动监控 / BUPT Activity Notifier

独立、开源的**只读**第二课堂活动监控原型。目标是从学生端活动 API 获取数据，按校区及签到/签退要求精细筛选，并通过微信/QQ 推送新增活动。

> **研究阶段 / Alpha**：已在登录后的微信小程序中实际看到活动数据，已从小程序前端源码确认活动接口及参数；但**独立 Python 请求、认证续期及长期稳定性尚未完成线上验收**。因此目前不能保证直接填入凭证就能运行。详见 [研究记录](docs/RESEARCH.md)。

## 功能

- 对接 `GET https://dekt.bupt.edu.cn/api/v1/activity`（未经公开文档承诺的内部接口）
- 识别 `area`（校区）和 `demands`（报名、签到、签退的位标志）
- 默认筛选 **沙河校区、需签到、不签退**
- 本地首次运行建立去重基线，避免把全部旧活动作为新活动推送
- 可选 [ServerChan](https://sct.ftqq.com/)（微信推送）与 OneBot v11 HTTP（QQ）
- 不执行报名、签到、签退、取消活动或订阅变更

## 已确认的数据规则

| 字段 | 含义 |
| --- | --- |
| `area = 0` | 西土城校区 |
| `area = 1` | 沙河校区 |
| `area = 2` | 线上 |
| `area = 3` | 海南校区 |
| `demands & 1` | 需要报名 |
| `demands & 2` | 需要签到 |
| `demands & 4` | 需要签退 |

筛选规则为：

```python
activity.area == 1 and (activity.demands & 2) != 0 and (activity.demands & 4) == 0
```

**重要：** 如果 `area` 或 `demands` 字段缺失，则该活动不匹配，而不是假定“不签退”。

## 安装

Python 3.10+：

```powershell
cd D:\Projects\bupt-activity-notifier
python -m pip install -e .
python -m unittest discover -s tests -v
python -m bupt_activity_notifier --demo
```

`--demo` 仅使用**虚构样例**，不联网，不需要账号。

## 配置与运行

```powershell
Copy-Item .env.example .env
# 在本地编辑 .env，并填写自己有权使用的第二课堂凭证、学籍相关查询参数
python -m bupt_activity_notifier --once --dry-run
python -m bupt_activity_notifier --once
# 接口验证成功后才建议持续运行：
python -m bupt_activity_notifier --watch
```

环境变量详见 [`.env.example`](.env.example)。`.env` 默认被 Git 忽略。

**认证注意：** 认证字段 `digest` 来源于小程序的登录用户上下文，不等同于活动 ID，也不保证与网页端 Token 通用。请勿将真实 Token、Digest、学号、Cookie、HAR、解包包体或用户信息上传 GitHub。目前不提供绕过身份认证或自动续期方案。

### 推送

在 `.env` 中设置 `SERVERCHAN_SENDKEY` 可推送至微信。QQ 通知需要自己控制的 OneBot v11 HTTP 端点，并配置 `ONEBOT_URL`、`ONEBOT_ACCESS_TOKEN` 及 `ONEBOT_USER_ID` 或 `ONEBOT_GROUP_ID`。

配置推送前可以使用 `--dry-run` 验证筛选。**第一次正常运行只建立基线、不推送历史活动**；此后只处理新增活动。状态存放在 `.state/seen.json`，该目录不会被 Git 跟踪。

## 项目结构

```text
src/bupt_activity_notifier/
  api.py             # 只读活动 API
  filtering.py       # 校区、签到和签退过滤
  monitor.py         # 轮询与去重
  notifications.py   # ServerChan / OneBot
  cli.py             # 命令行
tests/               # 离线单元测试
docs/RESEARCH.md     # 源码分析及待验收事项
```

## 范围与合规

本仓库是**独立实现**，没有包含微信小程序的解密包、原始 JS、后台数据或任何个人令牌。请以本人授权账号低频、只读使用，遵守学校系统规则及相应服务条款；官方内部接口可能随时改变。

原有的通知监控思路参考 [MaplumeX/bupt_notification](https://github.com/MaplumeX/bupt_notification)。本仓库重点是**活动列表**，不是校园新闻通知。
