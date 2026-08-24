# AI 前沿公众号文章生产线 · ai-daily

> 每日自动发现 AI 前沿话题，默认生成 1-2 篇、最多 3 篇独立公众号文章；完成调研、写作、扩写润色、标题测试、去 AI 味、封面/插图生成和质量自检后推送到个人微信与 QQ 邮箱。

```
RSS 信息源（11 源，英文一手 + 聚合 + 中文）
        │  GitHub Actions 定时抓取（北京时间 07:30）
        ▼
   选题编辑 ──── 事件聚类 + 实时性/前沿性/证据质量评分
        │
        ▼
   调研器 ───── 抓取原文 + 最多 4 个来源交叉验证 + 事实调研卡
        │
        ▼
   写作/终审 ── 标题 A/B 测试 + 初稿 + 扩写润色 + 去 AI 味 + 质量门禁
        │
        ▼
   配图编辑 ─── 尝试生成 1 张宽幅封面 + 0-5 张章节插图，失败则降级为文字版
        │
        ├──── article.* + images/（一题一文、图文排版）
        ├──── 提交图片后由 Server酱推送到个人微信
        └──── QQ SMTP 发送内嵌图文邮件
                     │
                     ▼
        人工：微信审稿 → 打开 HTML → 粘贴进个人公众号 → 发布
```

## 特性

- **11 个高质量信息源**：Google DeepMind 官方博客、arXiv、smol.ai AI News、The Rundown、TechCrunch/Verge/VentureBeat/MIT Tech Review、Hacker News 等；单源不可达不会拖垮日报
- **一题一文**：默认每日推荐 1-2 篇，硬上限 3 篇；每个最终话题生成独立文章目录
- **智能选题**：同一事件自动聚类，按实时性、前沿性、技术含量、证据质量和泛读者价值筛选
- **跨源调研**：每个话题抓取最多 4 个原文，生成带来源编号的事实、争议、不确定性和术语调研卡
- **完整编辑链**：初稿 → 扩写润色 → 过渡段整理 → 去 AI 味 → 终审，不直接发布一次生成结果
- **标题与摘要**：每篇生成 5 个标题方案并评分，选择最高分标题，同时生成公众号摘要
- **按需配图**：每篇尝试生成 1 张 900×383 封面；正文根据内容价值配置 0-5 张 1200×800 插图，并自动放在最相关章节后
- **内容型插图**：图像脚本来自文章本身，优先解释工作机制、结构关系和真实影响；禁止图中文字、水印、标志、伪造界面和虚构新闻现场
- **中文优先**：面向泛读者，普通概念不附英文翻译，只保留模型名、论文名、API、代码等必要技术术语
- **文字质量门禁**：自动检查篇幅、中文比例、引用覆盖、结构、AI 套话、标题质量和事实状态；不合格文章只输出待审核稿，不推送成品
- **配图柔性降级**：计划中的图片成功时输出图文版；不需要插图、密钥缺失或接口异常时继续输出并推送文字版，同时在 `article.json` 记录状态
- **跨天去重**：同时使用历史链接和历史话题标题，避免同一事件换链接重复发布
- **个人微信图文投递**：图片先提交到仓库，再把公网图片地址写入 Markdown，通过 Server酱 Turbo 推送到个人微信
- **QQ 邮箱图文投递**：通过 QQ SMTP 加密连接发送完整文章，图片以内嵌附件呈现，不依赖公网图片地址
- **双周自动清理**：每 14 天删除更早的 `output/日期/` 目录，并通过 QQ IMAP 只删除带项目专用标记的过期文章邮件
- **独立产物**：每篇文章都有公众号 HTML、Markdown、JSON；每日另有选题总览和标题测试索引
- **鲁棒设计**：RSS 并发抓取 + 超时重试、单源失败隔离、LLM 网络/格式异常自动降级、北京时间固定、Actions 并发保护
- **内容安全**：RSS 视为不可信数据，模型输出只接受真实候选链接，HTML/Markdown 统一净化且仅允许 HTTP(S) 链接
- **零服务器**：纯 GitHub Actions + Secrets；API 成本取决于文章数量、原文长度和模型价格

## 环境要求

- Python 3.11+
- GitHub 账号（用 Actions 定时运行，无需服务器）
- 任意 OpenAI 兼容 LLM API（推荐中文写作能力较好的模型）
- 支持图像生成的 OpenAI API key（默认使用 `gpt-image-2`；与文字模型密钥分开配置）
- Server酱 Turbo SendKey（用于个人微信推送，可先不配置）
- QQ 邮箱 SMTP 授权码（用于邮件推送，可先不配置；不能使用 QQ 登录密码）

## 快速开始

```bash
git clone git@github.com:<你的用户名>/ai-daily.git
cd ai-daily
python3 -m pip install -r requirements.lock

# 1. 配文字模型和图像模型（复制模板）
cp .env.example .env
# 填 LLM_API_KEY；正式图文成品还需填 IMAGE_API_KEY

# 2. 本地试跑（默认生成 1-2 篇、每篇约 2000 字）
python3 -m src.pipeline --articles 2 --target-chars 2000

# 3. 无 key 调试（不生成可发布成品、不触发微信）
python3 -m src.pipeline --dry-run

# 4. 微信图文推送推荐交给 Actions：图片会先提交，再投递公网地址

# 正式产物在 output/<北京时间日期>/ 下；dry-run 写入 output-dryrun/
```

## 部署到 GitHub（4 步）

详细分步见 [DEPLOY.md](./DEPLOY.md)（含验证点和失败排查表），核心动作：

1. **推送仓库**：`git remote add origin ... && git push -u origin main`
2. **配置文字、图像和投递 Secrets**（Settings → Secrets → Actions）：
   - `LLM_API_KEY` = 你的 DeepSeek key
   - `LLM_BASE_URL` = `https://api.deepseek.com/v1`
   - `LLM_MODEL` = `deepseek-v4-pro`
   - `IMAGE_API_KEY` = 你的 OpenAI API key
   - `IMAGE_BASE_URL` = `https://api.openai.com/v1`（可省略）
   - `IMAGE_MODEL` = `gpt-image-2`（可省略）
   - `WECHAT_SENDKEY` = 你的 Server酱 Turbo SendKey
   - `QQ_EMAIL_USER` = 作为发件人使用的完整 QQ 邮箱地址
   - `QQ_EMAIL_AUTH_CODE` = QQ 邮箱 SMTP 授权码，不是登录密码
   - `EMAIL_TO` = 收件邮箱（可省略，默认发给 `QQ_EMAIL_USER` 自己）
3. **手动触发验证**：Actions → AI Daily Digest → Run workflow，看日志全绿
4. **之后每天自动跑**：workflow 使用 `Asia/Shanghai` 时区，已配置北京时间 07:30

> 想换 OpenAI/Kimi/通义/GLM？只要 OpenAI 兼容接口，改 BASE_URL 和 MODEL 即可。

## 每日发布流程

1. 通过文字质量门禁的文章会分别推送到个人微信和 QQ 邮箱；配图成功时推送图文版，否则推送文字版。
2. 在微信中通读文章，重点核对事实、数字、标题和来源。
3. 打开仓库 `output/<北京时间日期>/article-XX/article_wechat.html`。
4. 浏览器打开 → 全选复制 → 粘贴到个人公众号编辑器；若编辑器没有带入本地图片，按原位置上传 `images/` 中对应文件。
5. 使用 `images/cover.jpg` 作为公众号封面，预览并人工发布。

个人公众号没有发布接口时，项目只负责把审稿成品送到微信，不模拟登录或绕过平台限制。

## 目录结构

```
ai-daily/
├── .github/workflows/
│   ├── daily-digest.yml                # 每日 07:30 定时任务
│   ├── biweekly-cleanup.yml             # 每 14 天清理过期输出和项目邮件
│   └── ci.yml                          # push / PR 自动测试
├── config/sources.yaml                 # 信息源清单（加源改这里）
├── src/
│   ├── fetcher.py                      # 并发 RSS 抓取 + 超时重试 + 去重
│   ├── curator.py                      # LLM 筛选、结构校验、异常降级
│   ├── history.py                      # 跨天已发布链接去重
│   ├── researcher.py                   # 原文抓取与跨源证据包
│   ├── writer.py                       # 调研卡、写作、润色与质量门禁
│   ├── illustrator.py                  # 可选封面/正文图生成、裁切与状态记录
│   ├── delivery.py                     # Server酱个人微信投递
│   ├── email_delivery.py               # QQ SMTP 图文邮件投递
│   ├── safety.py                       # 文本与 URL 安全边界
│   ├── renderer.py                     # 总览与独立文章渲染
│   └── pipeline.py                     # 入口
├── tests/                              # 单元与集成测试
├── templates/wechat.html               # 选题总览模板
├── templates/article.html              # 单篇公众号文章模板
├── .env.example                        # 文字、图像和微信配置模板
├── requirements.lock                   # Actions 使用的锁定生产依赖
├── requirements-dev.lock               # 测试依赖
├── DEPLOY.md                           # 部署与发布手册
└── output/YYYY-MM-DD/
    ├── digest.*                        # 当日选题总览
    ├── articles.json                   # 标题测试、评分与文章索引
    ├── article-01/
    │   ├── article.*                   # 第 1 个话题的独立文章
    │   └── images/                     # cover.jpg + 0-5 张正文插图
    └── article-02/                      # 第 2 个话题，结构相同
```

## 自定义（改完 commit + push 即生效）

- **加/删信息源**：`config/sources.yaml`（如加 `http://export.arxiv.org/rss/cs.RO` 盯具身智能论文）
- **改每日篇数**：`--articles 1` 到 `--articles 3`，默认 2
- **改文章长度**：`--target-chars 1600` 到 `--target-chars 3000`，默认 2000
- **调选题口味**：修改 `src/curator.py` 的 `TOPIC_PROMPT`
- **调写作和去 AI 味**：修改 `src/writer.py` 的写作、编辑提示词和质量门禁
- **调配图风格与质量**：修改 `src/illustrator.py`，或设置 `IMAGE_QUALITY=low|medium|high`
- **改排版**：编辑 `templates/article.html`（全部内联 CSS）
- **改时间窗**：workflow 里给 pipeline 加 `--window-hours 48`
- **改去重周期**：给 pipeline 加 `--history-days 14`；设为 `0` 可关闭
- **改清理保留期**：修改 `biweekly-cleanup.yml` 中两个 `14`；清理器只识别 `output/YYYY-MM-DD/`
- **改发布时间**：workflow 同时修改 `cron: '30 7 * * *'` 和 `timezone: 'Asia/Shanghai'`
- **自建 RSSHub**（可选，公共实例不稳时）：`docker run -d -p 1200:1200 diygod/rsshub`

## 测试

```bash
python3 -m pip install -r requirements-dev.lock
python3 -m pytest
```

每次 push / PR 都会由 CI 在 Python 3.11 上执行编译、Ruff 静态检查和测试。

## FAQ

**Q: 为什么不全自动发布？**
微信只对**已认证**订阅号开放草稿/发布 API，个人主体无法认证。第三方全自动工具有封号风险。最后人工 2 分钟顺便完成内容审核，对长期做号是好事。

**Q: 如何把文章推送到个人微信？**
在 [Server酱获取 SendKey](https://sct.ftqq.com/docs/getting-started/sendkey/)，把它保存为 GitHub Secret `WECHAT_SENDKEY`。SendKey 等同推送权限，不要提交到仓库或发到聊天中。
微信投递会把最终 Markdown 正文发送给 Server酱这一第三方服务；如果不接受该数据路径，不配置 SendKey 即可，文章仍会保存在仓库。

**Q: 如何推送到 QQ 邮箱？**
登录 [QQ 邮箱](https://mail.qq.com) 后，在设置的账户服务中开启 IMAP/SMTP 并生成授权码；把邮箱地址保存为 Secret `QQ_EMAIL_USER`，授权码保存为 `QQ_EMAIL_AUTH_CODE`。项目使用 `smtp.qq.com:465` 加密发送，并通过 `imap.qq.com:993` 清理过期项目邮件。授权码只放 Secrets，不要填写 QQ 登录密码。

**Q: 双周清理会删掉什么？**
仅删除保留期之外的 `output/YYYY-MM-DD/` 目录，以及收件箱/已发送中带 `X-AI-Daily: article` 专用邮件头的文章。其他输出文件、普通邮件和无法识别的目录都不会删除。工作流每周检查一次，由状态文件保证实际执行间隔不少于 14 天，也支持手动 `dry-run` 预览。

**Q: 为什么不能自动删除微信里的旧消息？**
Server酱正文会在服务端保存 1-3 天后自动过期，没有远程撤回微信客户端消息的接口。清理 `output/` 后旧消息中的仓库图片也会失效；微信聊天列表里的卡片如需删除，只能在微信客户端手动操作。

**Q: 为什么当天没有收到正式文章？**
系统宁可少发也不凑数。没有话题通过事实、篇幅、中文比例、引用和终审门禁时，只生成待审核稿，并发送人工检查提醒。配图失败不会触发这一门禁。

**Q: 为什么文章没有配图？**
配图是增强项，不影响文字文章发布。检查 `IMAGE_API_KEY`、账户余额、图像模型权限和 `article.json` 中的 `visuals.error`。部分 OpenAI 组织可能需要先完成图像模型的组织验证。

**Q: 微信里为什么看不到图？**
默认公网地址来自提交后的 GitHub 文件，因此仓库需要公开。私有仓库需把 `output/` 同步到可公开访问的 HTTPS 存储，并配置 Secret `PUBLIC_ASSET_ROOT_URL`；其目录下应能按 `日期/article-XX/images/文件名` 访问图片。

**Q: 某个 RSS 源一直失败？**
日志搜 `[FAIL]`。公共 RSSHub 实例不稳定是常态，方案见上面「自建 RSSHub」。

**Q: 周末/节假日条目太少？**
`python3 -m src.pipeline --window-hours 72`，或 workflow 加条件传参。

**Q: 想改成每周精选？**
cron 改 `0 1 * * 1`（每周一北京 09:00），`--window-hours` 调到 168。

## 贡献

欢迎 issue / PR：
- 加新的 RSS 源（直接改 `config/sources.yaml`）
- 改进 prompt（`src/curator.py`）
- 排版主题（`templates/wechat.html`）
- 修复 bug

## License

[MIT](./LICENSE) © 2026 huaiwei

随意使用、修改、分发，包括商用。如果对你有帮助，给个 star 就行 ⭐
