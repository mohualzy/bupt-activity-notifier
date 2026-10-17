# Edge 登录后自动同步第二课堂 Token（Windows）

状态：本机程序与离线测试已完成。**本人还需要在 Edge 中手动加载一次扩展；真实登录同步尚待端到端验收。**

## 工作原理

正常 Edge 打开 https://dekt.bupt.edu.cn/ 并完成学校要求的登录后，若该网页把 JWT 放入本网站的 localStorage 中名为 secondclass.tokenv3 的键，扩展将自动发现这个新凭证，通过 Edge 原生消息传送机制交给本机程序。

本机程序只在以下条件均成立时替换项目私有 Token：

- 与当前监控使用的 JWT 是同一用户 sub，login_type 也一致。
- 新 JWT 的过期时间明显晚于旧 JWT（至少 60 秒），距当前过期至少一小时。
- 使用新 JWT 实际访问官方学生端用户与活动 GET API，均通过 HTTP 200。
- 在校验到写入之间项目私有配置没有被手动更新。
- 仅原子更新项目 .env 的 SECONDCLASS_TOKEN，或已配置的本地私有 SECONDCLASS_TOKEN_FILE。不改微信推送、去重状态或 Windows 监控任务。

**重要限制：** 微信小程序登录、单独登录北邮 SSO 或其他门户，不一定会更新 Edge 里第二课堂这个键。网页管理端和学生端可能具有不同权限、不同登录类型，本机将拒绝不匹配的 Token。这不是无感自动登录，只是已有合法网页登录之后的自动同步。

## 一次性安装

本机 Native Messaging 程序通过 PowerShell 注册，无须管理员权限：

    cd D:\Projects\bupt-activity-notifier
    pwsh -NoProfile -File .\scripts\install_edge_token_sync.ps1

然后在你的正常 Edge 中：

1. 打开 edge://extensions
2. 启用“开发人员模式”，选择“加载解压缩的扩展”。
3. 选择项目**内部**目录：D:\Projects\bupt-activity-notifier\edge_token_sync
4. 检查安装后浏览器扩展 ID 为 mcohcjkicfoblidoolgbpladhehllpbb。
5. 在此 Edge 中正常进入 https://dekt.bupt.edu.cn/ 并登录或刷新。工具栏扩展弹窗可显示脱敏同步状态。

项目的可审查 C 源文件编译为一个小型 Windows EXE，只转发浏览器提供的标准输入、输出二进制消息管道，不开放本地 HTTP 端口，不访问网络。Windows Native Messaging 注册位于当前用户 HKCU 下，仅允许上述 Edge 扩展 ID。浏览器扩展只具有 nativeMessaging、storage 权限和对第二课堂官网的单域名内容脚本权限。

Edge 对解压缩扩展会显示开发模式警告，请只加载你认可并审核过的本仓库代码。如果今后移动项目目录，需重新注册主机并在 Edge 中重新加载扩展。

## 效果与问题排查

- “新 Token 已验证并更新”：学生端 API 已真正验证通过，新值原子写入原有私有凭证源，监控下一轮自动读取。
- “本机已使用这个 Token”：无须更新，不会再次访问学校。
- “不是更新版本 / 不同账号 / 登录上下文不同”：故意安全拒绝，原 Token 不受影响。
- “新 Token 无法通过学生端 API”：拒绝覆盖。这可能是管理端权限与学生端权限不同。
- “本机连接未启用”：确认 Edge 中已加载解压缩扩展、扩展 ID 一致、注册脚本成功。
- 没有弹窗通知时可点击扩展按钮查看最近状态。切勿把 JWT、Cookie 或 Ticket 发送至聊天。

自动同步不可用时，原有到期前微信提醒与手动续签继续有效。

## 卸载

先在 edge://extensions 关闭或移除扩展，再运行：

    pwsh -NoProfile -File .\scripts\install_edge_token_sync.ps1 -Uninstall

这只注销本机消息主机和其注册清单，不删除项目、.env、活动去重文件，也不停止监控任务。

## 安全边界

- 不读取 Edge Profile、Cookie、密码、CAS Ticket、其他网站或微信小程序。
- 不在扩展存储、Git、命令行参数或日志里保存 JWT。扩展存储只有状态枚举和时间。
- 不绕过验证码、MFA、学校风控或用户权限。
- 本机同用户恶意程序仍可能读取原本明文的 .env，本方案不解决设备被入侵的风险。
- 真实学生端 Token 传递仍需在你启用扩展并在官网完成正常登录后进一步验证，离线测试不能替代端到端结果。
