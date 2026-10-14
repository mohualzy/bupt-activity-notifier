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
- [ ] ServerChan / OneBot 用自己的账号进行真实发送
- [ ] 学校/小程序内部接口长期可用性与授权规则核对

## v0.3 工程可靠性验收（2026-10-14）

- 使用本地合成数据和 Mock 测试 Token 过期、私有文件轮换、HTTP `x-real-status`、拒绝重定向、认证异常脱敏。
- 通知采用按渠道回执：ServerChan 成功但 OneBot 失败后，可以只重试 OneBot，回执立即保存到本地状态文件。
- 本机启动回环 HTTP 模拟 OneBot 服务，成功收到了程序发出的真实 POST（完全虚构的测试活动）。
- 首次运行仍然只建立基线，不推送既有活动；旧版 `seen_ids` 状态可迁移。
- 增加 Docker Compose 与 GitHub Actions 构建入口；这些属于部署准备，**不代表生产环境已经运行**。
- `SECONDCLASS_TOKEN_FILE` 支持 watcher 重新读取合法获取的 Token；**不会自动登录、刷新凭证或绕过验证码**。

## 安全与开发边界

仓库中绝不保存微信小程序安装包、解包结果、个人学生数据、真实 Token 或 Digest。生产定时请求仅向官方 `https://dekt.bupt.edu.cn` 发起 `GET`；不请求报名、签到、签退、订阅或账号变更写接口。

真实接口虽已验证，但未被证明具有官方第三方开发支持。上线前应检查学校规则，合理频控；账号异常、HTTP 401/403 时停止相关操作，提示本人重新登录。
