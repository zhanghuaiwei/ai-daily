# 部署与每日发布手册

> 项目已完成选题、调研、单题写作、扩写润色、封面/插图生成、质量门禁、渲染、个人微信和 QQ 邮箱投递。
> 照下面做，全程约 10 分钟；之后每天由 GitHub Actions 自动运行。

---

## 阶段一：推送到 GitHub（本机，2 分钟）

**前置**：本机已装 git；GitHub 账号已配 SSH key（`ssh -T git@github.com` 能通）或用 HTTPS + token。

```bash
cd ai-daily

# 1. 先在 github.com 网页上新建一个空仓库（不要勾选 README/gitignore，要纯空的），名字建议 ai-daily

# 2. 关联并推送（二选一）
git remote add origin git@github.com:<你的用户名>/ai-daily.git   # SSH 方式
# git remote add origin https://github.com/<你的用户名>/ai-daily.git  # HTTPS 方式

git push -u origin main
```

**验证点**：刷新 GitHub 仓库页，能看到 `src/`、`config/`、`.github/workflows/` 目录。

## 阶段二：配置 Secrets（网页，2 分钟）

仓库页 → **Settings** → 左栏 **Secrets and variables** → **Actions** → **New repository secret**，逐个添加：

| Name | Value |
|---|---|
| `LLM_API_KEY` | 你的 OpenAI API key（`sk-` 开头） |
| `LLM_BASE_URL` | `https://api.openai.com/v1` |
| `LLM_MODEL` | `gpt-5.6-terra` |
| `LLM_REASONING_EFFORT` | `medium`（可省略） |
| `IMAGE_API_KEY` | 你的 OpenAI API key（图像生成使用） |
| `IMAGE_BASE_URL` | `https://api.openai.com/v1`（可省略） |
| `IMAGE_MODEL` | `gpt-image-2`（可省略） |
| `WECHAT_SENDKEY` | Server酱 Turbo 的 SendKey（用于个人微信推送） |
| `QQ_EMAIL_USER` | 完整 QQ 邮箱地址（发件账号） |
| `QQ_EMAIL_AUTH_CODE` | QQ 邮箱 SMTP 授权码，不能填写登录密码 |
| `EMAIL_TO` | 收件邮箱（可省略，默认与发件账号相同） |

> OpenAI API key 在 [API Keys](https://platform.openai.com/api-keys) 页面创建，只放 GitHub Secrets，不要提交到仓库。
> 默认文字模型为 [`gpt-5.6-terra`](https://developers.openai.com/api/docs/models/gpt-5.6-terra)；如果账户暂时没有该模型权限，可在确认可用模型后覆盖 `LLM_MODEL`。
> 配图默认使用 GPT Image 2。若接口提示模型权限问题，请检查余额，并按[图像生成官方说明](https://developers.openai.com/api/docs/guides/image-generation)完成必要的组织验证。
> 微信推送密钥在 [Server酱 SendKey 页面](https://sct.ftqq.com/docs/getting-started/sendkey/) 获取。密钥只放 GitHub Secrets，不要写进代码。
> QQ 邮箱需先在邮箱设置中开启 IMAP/SMTP 并生成授权码；项目使用 `smtp.qq.com:465` 发信，并通过 `imap.qq.com:993` 只清理带专用标记的过期项目邮件。

默认微信图片地址来自 GitHub，因此仓库应为公开仓库。私有仓库必须把 `output/` 同步到公开 HTTPS 存储，
再增加 Secret `PUBLIC_ASSET_ROOT_URL`（例如 `https://cdn.example.com/ai-daily/output`）。

## 阶段三：手动触发验证（网页，3 分钟）

1. 仓库页 → **Actions** 标签 → 左栏 **AI Daily Digest** → 右侧 **Run workflow** 按钮 → 绿色确认
2. 等运行出现（黄色转圈 → 绿色对勾），点进去看日志：
   - `Run pipeline` 应出现抓取、独立选题、原文调研、文章质量状态和配图状态
   - `Commit daily output` 步骤应有 `daily: <日期>` 提交
   - `Deliver articles to QQ Mail` 应显示邮件推送数量
   - `Deliver articles to WeChat` 应在提交之后推送图文文章
3. 个人微信与 QQ 邮箱收到文章；仓库 `output/<北京时间日期>/article-01/` 出现 HTML、Markdown、JSON 和 `images/` = 部署成功

**失败排查**：

| 日志现象 | 原因与处理 |
|---|---|
| `Run pipeline` 步骤红，提示缺 key | Secrets 名字拼错了，注意大小写：`LLM_API_KEY` |
| LLM 超时/鉴权/解析失败 | 生成待审核资料卡但不冒充正式文章；检查 Secrets、余额和模型名 |
| `IMAGE_API_KEY 未配置` | 正常生成并推送文字版；需要图文版时添加图像密钥后重跑 |
| 图像生成失败 | 自动降级为文字版；查看 `article.json` 的 `visuals.error`，检查图像模型权限、余额、超时和模型名 |
| `WECHAT_SENDKEY 未配置` | 文章仍会生成，但不会推送；按阶段二配置 Secret 后重跑 |
| QQ 邮箱账号或授权码未配置 | 文章和微信投递不受影响；配置 `QQ_EMAIL_USER` 与 `QQ_EMAIL_AUTH_CODE` 后重跑 |
| QQ 邮箱认证失败 | 确认已开启 IMAP/SMTP，Secret 中填写的是授权码而非登录密码；必要时重新生成授权码 |
| QQ 邮箱清理失败 | 确认 IMAP/SMTP 均已开启；文章发送不受影响，下次清理仍可重试 |
| 没有文章通过质量门禁 | 微信收到人工检查提醒；这只由文字与事实质量决定，与配图是否成功无关 |
| 微信正文显示裂图 | 公开仓库检查图片 URL；私有仓库配置能公开访问图片的 `PUBLIC_ASSET_ROOT_URL` |
| 个别源 `[FAIL]` | 正常（源偶尔抽风会自动跳过）；全失败才需要查网络 |
| `Commit daily output` push 冲突 | workflow 会先 rebase；仍冲突时保留日志并手动重跑，不会静默忽略 |
| 定时任务不触发 | GitHub cron 常态性延迟几分钟到几小时，耐心等或手动 Run |

## 阶段四：每日发布到公众号（每天 2-5 分钟）

1. 在个人微信或 QQ 邮箱查看通过文字质量门禁的独立文章；有图时为图文版，无图时为文字版。
2. 打开仓库 `output/<北京时间日期>/article-XX/article_wechat.html` → 下载或本机打开。
3. 浏览器打开 → `Cmd/Ctrl+A` 全选 → `Cmd/Ctrl+C`。
4. [mp.weixin.qq.com](https://mp.weixin.qq.com) → 新建图文 → 正文粘贴；若本地图片未随复制带入，按文章位置上传 `images/illustration-01.jpg` 和 `illustration-02.jpg`。
5. 通读事实与来源 → 上传 `images/cover.jpg` 作为封面 → 预览 → 发布。

内联 CSS 会完整保留，粘贴即成品排版。MD 版可同步发布，JSON 版用于归档、去重和二次开发。

---

## 日常自定义（改完 commit + push 即生效）

- **加/删信息源**：`config/sources.yaml`（例如加 `http://export.arxiv.org/rss/cs.RO` 盯具身智能论文）
- **改每日篇数**：pipeline 命令使用 `--articles 1` 到 `--articles 3`
- **改目标篇幅**：pipeline 命令使用 `--target-chars 1600` 等参数
- **调选题标准**：`src/curator.py` 的 `TOPIC_PROMPT`
- **调写作与去 AI 味**：`src/writer.py` 的提示词和 `article_metrics`
- **调封面/插图风格**：`src/illustrator.py`；图像质量由 `IMAGE_QUALITY` 控制
- **改排版样式**：`templates/article.html`
- **调整抓取时间窗**：`.github/workflows/daily-digest.yml` 里给 pipeline 命令加 `--window-hours 48`
- **调整跨天去重**：pipeline 命令加 `--history-days 14`；`0` 表示关闭
- **改发布时间**：同时修改 workflow 的 `cron` 和 `timezone`，默认是北京时间 07:30
- **改双周清理策略**：`.github/workflows/biweekly-cleanup.yml`；默认保留最近 14 天

## 双周清理边界

- `output/`：仅清理名字严格匹配 `YYYY-MM-DD` 且超过 14 天的普通目录；符号链接和异常路径会拒绝处理。
- QQ 邮箱：仅在收件箱和服务器标记为“已发送”的文件夹中，删除同时满足“项目专用邮件头”和“超过 14 天”的邮件。
- 微信：Server酱服务端正文免费版约 1 天、会员版约 3 天后自动过期；微信客户端消息不支持程序远程撤回，只能手动删除。
- 工作流每周一北京时间 03:20 检查，由 `.maintenance/cleanup-state.json` 保证实际清理间隔不少于 14 天。手动运行时可选择 `dry_run` 只预览。

## 安全提醒

- `.env`（本地调试用）已被 gitignore，**永远不要**把 key 写进代码或提交记录
- 对话/剪贴板里出现过的 key，用完建议去后台 rotate（重新生成）
- `WECHAT_SENDKEY` 等同于给个人微信发送消息的权限，同样只能放 Secrets
- `QQ_EMAIL_AUTH_CODE` 等同于第三方客户端发信权限，只能放 Secrets；泄露后立即在 QQ 邮箱撤销
- `IMAGE_API_KEY` 会产生图像生成费用，应设置账户预算和用量告警
- 微信投递会经过 Server酱第三方服务；不配置 SendKey 时只生成本地/仓库产物
- RSS 和 LLM 输出都按不可信内容处理；不要移除 URL 白名单、输出净化或人工发布前审核
