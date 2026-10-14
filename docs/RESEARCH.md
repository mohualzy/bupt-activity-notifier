# 第二课堂学生端活动 API 实证记录

更新：2026-10-14。本文只发布自行整理的接口事实和统计摘要，不包含学生身份信息、原始解密 JS、访问令牌、用户 Digest、Cookie 或完整抓包。

## 实测：已通过

- 电脑微信小程序“北邮第二课堂”的学生端活动列表，能够显示活动标题、日期、校区、位置、报名、签到、签退和主办方。
- 小程序包只读静态分析确认登录后获取用户数据，再读取校园活动列表。
- 使用 Edge **本人已登录的网页会话**，通过只读 GET 得到用户上下文 HTTP 200；再以该上下文读取活动列表 HTTP 200。
- 使用本机**一次性回环内存通道**向 Python requests 提供当前有效 Token，Python **独立**完成两次 GET，均 HTTP 200。此测试未将 Token 保存到磁盘；临时测试服务结束后自动关闭。
- 两种方式均返回 **19 条校园活动、1 条匹配默认筛选规则**；这是**当时的列表快照**，并非全校活动总数。

### 用户上下文

```http
GET https://dekt.bupt.edu.cn/api/v1/user/{currentUserId}
Authorization: Bearer <private JWT>
```

`currentUserId` 来源于有效 JWT 的 `sub` 声明，服务器负责验证 JWT。响应结构（仅列字段名）：

```json
{
  "status": "ok",
  "data": {
    "id": "...",
    "college_id": "...",
    "class_id": "...",
    "grade": "...",
    "role_id": "..."
  },
  "digest": "...",
  "error": null
}
```

`digest` 是用户上下文响应的顶层字段，而非 `data.digest`。

### 校园活动

```http
GET https://dekt.bupt.edu.cn/api/v1/activity
    ?college_id=<from user.data>
    &class_id=<from user.data>
    &grade=<from user.data>
    &role_id=<from user.data>
    &digest=<from user.digest>
    &is_group=0
Authorization: Bearer <private JWT>
```

响应顶层键为 `status`、`data`、`digest`、`error`；`data` 是活动数组，`digest` 是与活动列表对应的摘要数组。单条活动至少包含 `id`、`name`、`area`、`demands`、`location`、`activity_start_time`、`activity_end_time` 等键。

### 字段编码

```text
area: 0 西土城校区, 1 沙河校区, 2 线上, 3 海南校区, 100000000 其他
demands: bit 0 (1) 需报名；bit 1 (2) 需签到；bit 2 (4) 需签退
```

规则：`area == 1 and bool(demands & 2) and not bool(demands & 4)`。不完整数据必须跳过，不假定免签退。

另外：`GET /api/v1/activity/{id}` 是活动详情；`GET /api/v1/activity/class` 是分类；`GET /api/v1/participation/acts` 为本人参与活动列表，而**不是**校园活动主页。

## 未完成 / 不应夸大的能力

- [x] 小程序真实列表/详情已观察
- [x] 独立 Python HTTP 200 和返回字段确认
- [x] 自动从用户 GET 响应取得 `digest`
- [x] 默认筛选及去重逻辑离线测试
- [ ] 长期 Token 续期/会话恢复方案（当前仅支持有效 Token）
- [ ] 长时间运行的速率与稳定性验收
- [ ] 校区、签到要求修改后的真实推送行为回归
- [x] ServerChan 使用本人配置的 SendKey 发送虚构测试活动，接口报告成功，用户确认微信端实际收到（2026-10-14）
- [ ] OneBot 使用本人可控的真实 QQ 账号完成送达验收（仅本机模拟 HTTP 已通过）
- [ ] 学校/小程序内部接口长期可用性与授权规则核对

## v0.3 工程可靠性验收（2026-10-14）

- 使用本地合成数据和 Mock 测试 Token 过期、私有文件轮换、HTTP `x-real-status`、拒绝重定向、认证异常脱敏。
- 通知采用按渠道回执：ServerChan 成功但 OneBot 失败后，可以只重试 OneBot，回执立即保存到本地状态文件。
- 本机启动回环 HTTP 模拟 OneBot 服务，成功收到了程序发出的真实 POST（完全虚构的测试活动）。
- 首次运行仍然只建立基线，不推送既有活动；旧版 `seen_ids` 状态可迁移。
- 增加 Docker Compose 与 GitHub Actions 构建入口；这些属于部署准备，**不代表生产环境已经运行**。
- `SECONDCLASS_TOKEN_FILE` 支持 watcher 重新读取合法获取的 Token；**不会自动登录、刷新凭证或绕过验证码**。

## 微信端真实推送验收（2026-10-14）

- 使用本地被 Git 忽略的 `.env` 配置 ServerChan SendKey；未把真实密钥输出到终端、聊天或仓库。
- 运行 `python -m bupt_activity_notifier --test-push`，发送一条**虚构且明确标记为测试**的活动通知；程序显示 `Test notification accepted by configured provider(s).`，退出码为 `0`。
- 用户随后明确确认**本人微信端确实收到了该消息**，所以 ServerChan → 微信的真实端到端测试判定 **PASS**。
- 该结果只证明测试通知送达；不代表第二课堂持续轮询、真实活动触发的推送或 OneBot QQ 送达已完成验收。

## 实际账号全链路查询与轮询验收（2026-10-14）

- 使用本人保存在本地、被 Git 忽略的 `.env` 凭证运行 `--doctor`，第二课堂只读接口返回 HTTP 200，获取 19 条活动。
- 使用 `--once --dry-run` 按沙河校区 / 需签到 / 无签退的位规则筛选出 1 条匹配活动；干跑没有写状态或发送微信消息。
- 首次 `--once` 仅建立持久化基线（`.state/seen.json`，1 个活动），没有推送既有活动；第二次 `--once` 为 0 条新匹配、0 次投递。
- 将真实 `2026-10-16T10:50:00Z` 至 `2026-10-16T12:05:00Z` UTC 活动时间换算为**北京时间 2026-10-16 18:50–20:05**，并增加明确时区、无时区及错误时间的测试。
- 启动 `--watch` 进行一次短时真实查询：成功进入 300 秒轮询模式，返回 19 条活动 / 1 条符合 / 0 条新匹配 / 0 次推送。**随后主动终止测试进程，没有开通常驻守护运行。**
- 整套测试 51/51 通过。此次验收不证明连续运行数天的可靠性，也不代表发生新活动时真实微信推送的联合场景已发生。

## Windows 登录自启与凭证过期提醒验收（2026-10-14）

- 在本机当前用户权限下注册 **`BUPT-SecondClass-Activity-Watcher`** Windows 登录任务，`pythonw.exe` 无控制台后台启动，任务状态 **Running**，独立 Python 进程持续存在。
- 在实际已配置的第二课堂账户上完成该后台进程的首轮只读查询：**19 条返回、1 条符合筛选、0 条新匹配、0 次通知投递**；不重发历史活动。
- 配置 `MultipleInstances=IgnoreNew` 并用 Windows 文件锁双重防重复运行；人工另启同一监控入口后立即退出，存活 watcher 数量仍为 **1**。
- 本地日志 `logs/watch.log` 已真实写入首次查询结果；日志、`.env`、`.state` 均被 Git 忽略。
- `--watch` 每轮重新读取 `.env`；校验 JWT 到期前 24 小时、到期后两种微信/QQ 提醒的模拟发送、逐渠道回执和重复抑制。**过期提醒尚未触发真实外发**（验收时登录凭证仍有约 67 小时剩余）。
- 此次只证明后台任务**已成功启动和首轮运行**，不能替代重启电脑后的自动启动验收、电脑睡眠/断网恢复或数日可靠性实验。

## 真实新活动触发通知记录（2026-10-14）

- Windows 常驻 watcher 在 **16:16** 发现学生端活动接口列表由先前的 19 条变为 **21 条**，符合默认沙河 / 签到 / 无签退筛选的活动由 **1 条增至 2 条**。
- 日志明确记录 `Notified activity 13311.`，对应 `Fetched=21, matched=2, new_matches=1, completed=1, deliveries=1`。依据代码语义，这是通知渠道接口确认成功后才会写入的活动送达回执；**不代表此刻已由使用者确认手机实际收到了该条消息**。
- 16:21、16:26、16:31 等后续轮询均为 `new_matches=0`、`deliveries=0`，说明同一活动没有在这些轮询中重复通知。
- 原有微信 `--test-push` 的手机真实收到测试仍是单独证据；新活动微信实际到达手机待本人确认。

## 安全与开发边界

仓库中绝不保存微信小程序安装包、解包结果、个人学生数据、真实 Token 或 Digest。生产定时请求仅向官方 `https://dekt.bupt.edu.cn` 发起 `GET`；不请求报名、签到、签退、订阅或账号变更写接口。

真实接口虽已验证，但未被证明具有官方第三方开发支持。上线前应检查学校规则，合理频控；账号异常、HTTP 401/403 时停止相关操作，提示本人重新登录。
