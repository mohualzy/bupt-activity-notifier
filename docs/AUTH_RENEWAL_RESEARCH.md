# 第二课堂 Token 自动续期可行性调研

日期：2026-10-14。范围：用户已授权使用的第二课堂网页 `https://dekt.bupt.edu.cn`、公开前端 JavaScript，及一次经用户明确要求进行的**本人现有 Edge 浏览器 SSO 跳转实测**。研究人员仅发起公开 GET 和浏览器官方 CAS 导航；浏览器可按官方页面逻辑自行发起换票请求。研究工具未手动提交账号密码、Ticket 或认证 POST，不导出 Cookie，不查看、记录或复制 Token/Ticket 值。

## 结论

**当前不具备可靠、已证实的“仅凭已有第二课堂 Token 无人值守自动续期”方案。**

在当日网页入口、登录模块和入口列出的 58 个按需加载 JavaScript 文件中，未发现标准 `refresh_token`、`refreshToken` 或明确的普通用户 token refresh URL/调用流程。不能据此断言服务端不存在任何未公开接口；只能说前端代码没有提供可信的续期协议。

目前 v0.4 方案是：Token 到期前 24 小时由配置的微信/QQ 渠道通知，用户在合法会话中重新获取 JWT，修改本地被 Git 忽略的 `.env` 的 `SECONDCLASS_TOKEN` 后，正在运行的 `--watch` 下一轮自动读取、恢复查询；不需要重启。

## 公开前端的实际认证结构

入口 `https://dekt.bupt.edu.cn/landing`（2026-10-14 HTTP 200）加载：

- `https://dekt.bupt.edu.cn/static/js/index.af1222c4.js`
- `https://dekt.bupt.edu.cn/static/js/async/6899.67b1cc60.js`（按需加载的普通网页登录模块）
- `https://dekt.bupt.edu.cn/static/js/async/5621.038caa8c.js`（按需加载的北邮统一认证回跳模块）
- `https://dekt.bupt.edu.cn/static/js/async/8676.85a4b2b5.js`（企业微信 OAuth 回跳模块）
- `https://dekt.bupt.edu.cn/static/js/async/1390.92a23c5d.js`（用户侧工具模块之一）

这些静态文件路径及构建哈希会随官网更新改变。

### Token 存储、使用、失效

1. 网页读写 `localStorage["secondclass.tokenv3"]`（如果嵌入容器，也支持 `embedToken`）；JWT 内含 `sub` 与 `exp`。
2. 网页 HTTP 请求拦截器直接把当前 Token 拼成 `Authorization: Bearer <token>`。遇到失败只有网络 GET 重试／错误提示；没有观察到获取新 Token 再重放原请求的拦截器。
3. 页面加载时会检查 JWT 到期时间与 `login_type`，是否能完成用户资料 GET；这一逻辑**不是**延长 JWT 有效期。
4. 项目 v0.4 通过当前 JWT 访问官方只读 `/api/v1/user/{currentUserId}` 和 `/api/v1/activity`，只在 JWT 未过期时查询。

### 新建会话的接口不是“刷新接口”

| 前端调用 | 前端用途 | 对无人值守续期的意义 |
| --- | --- | --- |
| `POST /api/v1/auth/sessions` | 网站账号密码登录，携带验证码字段 `captcha` / `code` | **重新登录**；并非已证实的 JWT refresh；不能假定可跳过验证码或安全储存密码 |
| `POST /api/v1/auth/bupt/sessions` | 北邮统一认证成功后，使用回跳 `ticket` 换取第二课堂 JWT | 已在本人 Edge 中观察到 CAS **免输密码签发 Ticket 并重定向到此回调页面**；**换票是否成功生成可用于该账号的 JWT 尚未证实** |
| `POST /api/v1/wecom/auth/sessions` | 企业微信 OAuth 回调 `code` 登录 | 依赖企业微信授权回跳，不是通用 refresh |
| `POST /api/v1/auth/sessions/sudo` | 高权限账户生成 `sudo` / 超管环境临时会话 | **不是学生 Token 更新接口，不应调用来续期** |

对最后一个接口，公开模块 `1390.92a23c5d.js` 表明按钮受 JWT 中管理权限级别 `>= 3` 且当前非 `sudo` 环境的条件控制，随后打开附带 `#env=sudo` 的 `auth.token-land` 页面。不能因接口名称中包含 `sessions` 就当作普通刷新使用。

## 与北邮统一身份认证 OAuth 的区别

公开第三方项目 [byrdocs/bupt-auth](https://github.com/byrdocs/bupt-auth/blob/main/index.ts) 为 **`apiucloud.bupt.edu.cn/ykt-basics/oauth/token`** 实现 `grant_type=refresh_token`，其 `refresh_token` 属于北邮云平台 OAuth 体系，并非本项目观察到的第二课堂 `secondclass.tokenv3`。**不能把第二课堂 JWT 直接传给该 OAuth 接口，也不能把其刷新逻辑套用到第二课堂。**

## Edge 浏览器 SSO 受控实测（2026-10-14）

**测试目标：** 在不读取 Cookie、密码或 Ticket 值的前提下，验证当前本人 Edge 的 CAS 单点登录是否仍有效，以及第二课堂能否从 CAS 回调恢复登录。

**方法与证据：**

1. 浏览器已有北邮信息服务门户登录页，以及第二课堂网页会话。使用不带浏览器 Cookie 的匿名 `requests.get` 访问北邮官方 `https://auth.bupt.edu.cn/authserver/login`，附上实验用 `service` 地址后，返回 **HTTP 200 / CAS 登录表单**，说明匿名会话不能免登录。
2. 在本人已登录的 **Edge** 中打开同一官方 CAS 地址，实验性的 `service` 参数指向 `https://dekt.bupt.edu.cn/bupt-login`（**这是根据网页路由推定的候选值，尚未从校方文档证实是注册的完整 Service URI**）。
3. 浏览器未要求输入用户名、密码或验证码，自动返回第二课堂的 **`/bupt-login`** 路径。只检查 URL **查询参数名称**，确认存在 `ticket` 字段；未读取、显示、保存其值。**阶段 A：已证实同一浏览器会话能免交互取得 CAS Ticket（PASS）。**
4. 第二课堂回调页面曾短暂显示“登录成功”，但随后新开 `/landing` 仍回到 `/login`；另一轮在 DevTools 打开时停留在 `/bupt-login`。因此无法确认换票 HTTP 状态、最终可用 JWT、同一用户 `sub` 或新 `exp`。**阶段 B：第二课堂 Ticket → 有效新 JWT（未通过验收），不能把“登录成功”提示当作完成证据。**
5. 本次未把 CAS Ticket 提交给其他服务，没有主动手工调用换票 POST，没有修改本地 `.env`，没有开启自动认证轮询；没有改变既有后台监控代码。

**未解决的关键因素：** 第二课堂注册的精确 CAS Service URI 可能并非本次实验 URI；其次可能存在页面路由、第二课堂账号权限或 Ticket 换票错误。仅通过页面短暂提示不能区分这些原因。需要使用经授权的官方回调 URI 和**只记录 HTTP 状态、不收集请求体及敏感 URL**的调试方法完成下一轮定向验证。

**阶段判定：** SSO 浏览器已有会话 → CAS Ticket **PASS**；CAS Ticket → 第二课堂有效 JWT **UNVERIFIED**；把 JWT 无人值守同步至本地监控 **NOT IMPLEMENTED**。任何 SSO 登录状态及 CAS Cookie 都可能另行过期，故无法保证永久免费登录。

## 自动续期候选路线与评价

| 路线 | 当前判定 | 前提 / 风险 |
| --- | --- | --- |
| A. 直接 refresh JWT | **No-Go（缺失协议证据）** | 需学校官方或后台开发者提供 refresh URL、输入凭证类型、返回字段、失效机制和明确许可 |
| B. 借助现有学校 SSO 登录态重新取得第二课堂 Token | **第一步 PASS；端到端仍 No-Go** | 本人 Edge 的既有 SSO 会话可免输入密码取得一次性 Ticket，但第二课堂应用随后回到登录页；需进一步确认官方受信任的 service 回调 URI、换票结果、账户权限及 Cookie 时效 |
| C. 存储账号密码自动重登 | **不推荐** | 扩大高价值凭证暴露面；验证码、MFA、频控、会话挑战可能使其失效，不应尝试规避 |
| D. 用户手动续期 + Watcher 自动热更新 | **已上线且已验证** | 到期前通知用户，重新登录并替换本地 `.env`，无需重启、无额外账号密码存储 |

### 继续研究路线 B 前必须满足的验收门

1. 只在本人有权使用的账号与已授权浏览器会话上操作；不把 Cookie、Ticket、Token 发送至聊天、日志或第三方。
2. 取得校方许可或可核实的公开文档，确认该 SSO 路径允许个人应用自动重新授权；**不伪造或绕过验证码、MFA**。
3. 明确 SSO Cookie 自身的有效期与自动恢复机制；不以“浏览器目前已登录”冒充永久认证。
4. 构造一次带身份许可的完整合法 SSO 流程，以脱敏方式核验新 JWT 的 `sub` 不变、`exp` 晚于原值，以及只读第二课堂活动查询 HTTP 200。
5. 避免在浏览器中运行第三方取密钥脚本或持续暴露调试端口；新凭证只存储在受保护的本地文件中。
6. 401/403、验证码或重新认证要求出现时**立即停下并提示本人**，不能反复尝试或自动回退到密码爆破。

## 目前系统的实际保证

- Windows 登录自启的监控任务已启动，按 300 秒查询，仅访问第二课堂的只读活动接口。
- `--watch` 每轮重新加载 `.env`，更新 `SECONDCLASS_TOKEN` 后无需重启监控。
- 预计到期前 24 小时和过期后分别最多通过已配置渠道提醒一次（该提醒发送逻辑在合成测试中验证，尚未到实际触发时刻）。
- **本次调研不修改认证程序、不调用未知认证接口、不消耗登录次数、不承诺永久免登录。**

最终决策：维持现有可靠的人工授权续期方案；除非取得可核实的学校侧刷新协议或完成合法 SSO 重新授权验证，否则不实现宣称“全自动续期”的脚本。
