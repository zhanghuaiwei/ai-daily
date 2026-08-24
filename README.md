# AI 前沿日报 · ai-daily

> 每日自动抓取全球 AI 资讯 → DeepSeek 筛选 3-5 条高价值内容 + 推荐理由 → 生成**公众号可直接粘贴的成品 HTML**。
> 你只需 2 分钟复制粘贴发布，剩余全自动。

```
RSS 信息源（11 源，英文一手 + 聚合 + 中文）
        │  GitHub Actions 定时抓取（北京时间 07:30）
        ▼
   DeepSeek 筛选器 ──── 挑 3-5 条 + 写"为什么值得关注"
        │
        ▼
   渲染器 ──── digest.md        （存档 / 知乎掘金同步发）
        └──── digest_wechat.html（内联 CSS 公众号成品）
                     │
                     ▼
        人工：打开 HTML → 全选复制 → 粘贴进公众号编辑器 → 发布
              （个人号无发布 API，最后一步手动，约 2 分钟）
```

## 特性

- **11 个高质量信息源**：Google DeepMind 官方博客、arXiv、smol.ai AI News、The Rundown、TechCrunch/Verge/VentureBeat/MIT Tech Review、Hacker News 等，实测全部可达
- **真 AI 筛选**：DeepSeek v4-pro 重写中文摘要 + 写推荐理由，不是关键词匹配的占位文案
- **双格式产出**：公众号 HTML（内联 CSS，粘贴即成品排版）+ Markdown（同步发知乎/掘金/博客）
- **多样性保障**：payload 按源轮询采样 + prompt 硬约束（论文类最多 2 条），避免日报被单一来源刷屏
- **鲁棒设计**：单源失败自动跳过、LLM 输出异常自动降级兜底、思考模型超时 300s 容错
- **零服务器**：纯 GitHub Actions + Secrets，每天成本约几分钱

## 环境要求

- Python 3.11+
- GitHub 账号（用 Actions 定时运行，无需服务器）
- 任意 OpenAI 兼容 LLM API（推荐 DeepSeek，便宜且中文摘要质量好）

## 快速开始

```bash
git clone git@github.com:<你的用户名>/ai-daily.git
cd ai-daily
pip install -r requirements.txt

# 1. 配 LLM（复制模板，填你的 DeepSeek key）
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY=sk-你的key

# 2. 本地试跑（带 AI 筛选）
python -m src.pipeline

# 3. 无 key 调试（跳过 LLM，用兜底排序，验证抓取和渲染）
python -m src.pipeline --dry-run

# 产物在 output/<今天日期>/ 下
```

## 部署到 GitHub（4 步）

详细分步见 [DEPLOY.md](./DEPLOY.md)（含验证点和失败排查表），核心动作：

1. **推送仓库**：`git remote add origin ... && git push -u origin main`
2. **配 3 个 Secrets**（Settings → Secrets → Actions）：
   - `LLM_API_KEY` = 你的 DeepSeek key
   - `LLM_BASE_URL` = `https://api.deepseek.com/v1`
   - `LLM_MODEL` = `deepseek-v4-pro`
3. **手动触发验证**：Actions → AI Daily Digest → Run workflow，看日志全绿
4. **之后每天自动跑**：cron 已配置北京时间 07:30

> 想换 OpenAI/Kimi/通义/GLM？只要 OpenAI 兼容接口，改 BASE_URL 和 MODEL 即可。

## 每日发布流程（半自动，2-5 分钟）

1. 打开仓库 `output/<今天>/digest_wechat.html`
2. 浏览器打开 → `Cmd/Ctrl+A` 全选 → `Cmd/Ctrl+C`
3. [mp.weixin.qq.com](https://mp.weixin.qq.com) → 新建图文 → 粘贴
4. 通读审核 → 加封面 → 预览 → 发布

MD 版（`digest.md`）可同步发知乎/掘金/个人博客。

## 目录结构

```
ai-daily/
├── .github/workflows/daily-digest.yml  # 每日 07:30 定时任务
├── config/sources.yaml                 # 信息源清单（加源改这里）
├── src/
│   ├── fetcher.py                      # RSS 抓取 + 去重 + 时间窗过滤
│   ├── curator.py                      # LLM 筛选（含兜底 + 源轮询采样）
│   ├── renderer.py                     # 渲染 Markdown + 公众号 HTML
│   └── pipeline.py                     # 入口
├── templates/wechat.html               # 公众号排版模板（内联 CSS）
├── .env.example                        # LLM 配置模板
├── DEPLOY.md                           # 部署与发布手册
└── output/YYYY-MM-DD/                  # 每日产物（Actions 自动 commit）
```

## 自定义（改完 commit + push 即生效）

- **加/删信息源**：`config/sources.yaml`（如加 `http://export.arxiv.org/rss/cs.RO` 盯具身智能论文）
- **调筛选口味**：`src/curator.py` 的 `PROMPT`（价值排序 / 偏好主题 / 论文配额）
- **改排版**：`templates/wechat.html`（全内联 `style=""`，改配色字号直接编辑）
- **改时间窗**：workflow 里给 pipeline 加 `--window-hours 48`
- **改发布时间**：workflow 里 `cron: '30 23 * * *'`（UTC，北京时间 = UTC+8）
- **自建 RSSHub**（可选，公共实例不稳时）：`docker run -d -p 1200:1200 diygod/rsshub`

## FAQ

**Q: 为什么不全自动发布？**
微信只对**已认证**订阅号开放草稿/发布 API，个人主体无法认证。第三方全自动工具有封号风险。最后人工 2 分钟顺便完成内容审核，对长期做号是好事。

**Q: 某个 RSS 源一直失败？**
日志搜 `[FAIL]`。公共 RSSHub 实例不稳定是常态，方案见上面「自建 RSSHub」。

**Q: 周末/节假日条目太少？**
`python -m src.pipeline --window-hours 72`，或 workflow 加条件传参。

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
