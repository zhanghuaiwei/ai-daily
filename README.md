# AI 前沿日报流水线

每天早上 7:30 自动抓取全球 AI 资讯源 → LLM 筛选 3-5 条高价值内容 + 推荐理由 → 生成**公众号可直接粘贴的成品 HTML**。你只需花 2 分钟复制粘贴发布。

```
RSS 信息源(英文一手 + 聚合 + 中文)
        │  GitHub Actions 定时抓取（每日 07:30）
        ▼
   LLM 筛选器 ──── 挑 3-5 条 + 写"为什么值得关注"
        │
        ▼
   渲染器 ──── digest.md（存档）
        └──── digest_wechat.html（内联 CSS 成品）
                     │
                     ▼
        人工：打开 HTML → 全选复制 → 粘贴进公众号编辑器 → 发布
              （个人号无发布 API，最后一步手动，约 2 分钟）
```

## 目录结构

```
ai-daily/
├── .github/workflows/daily-digest.yml  # 定时任务
├── config/sources.yaml                 # 信息源清单（想加源改这里）
├── src/
│   ├── fetcher.py                      # RSS 抓取 + 去重 + 时间窗过滤
│   ├── curator.py                      # LLM 筛选（含无 key 兜底逻辑）
│   ├── renderer.py                     # 渲染 Markdown + 公众号 HTML
│   └── pipeline.py                     # 入口：python -m src.pipeline
├── templates/wechat.html               # 公众号排版模板（改样式看这里）
└── output/YYYY-MM-DD/                  # 每日产物（Actions 自动 commit）
```

## 快速开始（本地先跑通）

```bash
cd ai-daily
pip install -r requirements.txt

# 无 API key 调试：跳过 LLM，用兜底排序，验证抓取和渲染没问题
python -m src.pipeline --dry-run

# 产物在 output/<今天日期>/ 下
```

## 部署到 GitHub（4 步）

**第 1 步：建仓库并推送**

```bash
cd ai-daily
git init && git add -A && git commit -m "init: ai daily pipeline"
git remote add origin git@github.com:<你的用户名>/ai-daily.git
git push -u origin main
```

**第 2 步：配置 LLM Secrets**

仓库页面 → Settings → Secrets and variables → Actions → New repository secret，添加三个（**推荐 DeepSeek**：便宜、中文摘要质量好、实测可通）：

| Secret 名 | 值 | 说明 |
|---|---|---|
| `LLM_API_KEY` | 你的 DeepSeek key | 必填 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | 用 OpenAI 官方可填 `https://api.openai.com/v1` |
| `LLM_MODEL` | `deepseek-v4-pro` | 求质量用 pro，省钱用 `deepseek-v4-flash` |

> 任意 OpenAI 兼容服务都行：DeepSeek（便宜，中文好）、Kimi、通义、GLM、OpenAI。筛选任务每天只调 1 次，成本几乎可以忽略。

**第 3 步：手动触发一次验证**

仓库 → Actions → AI Daily Digest → Run workflow → 看日志是否全绿。
成功后 `output/<日期>/` 会出现当日产物。

**第 4 步：之后每天自动跑**

cron 已配置为北京时间 07:30，无需再管。
> GitHub 的 cron 不保证准时，可能延迟几分钟到半小时，属正常现象。

## 每日发布流程（半自动的"手动"部分）

1. 打开仓库里 `output/<今天>/digest_wechat.html`（本地 pull 下来或点文件 → raw 下载）
2. 浏览器打开它 → `Ctrl/Cmd + A` 全选 → `Ctrl/Cmd + C` 复制
3. 公众号后台 mp.weixin.qq.com → 新建图文 → 正文区 `Ctrl/Cmd + V` 粘贴
4. 通读一遍（顺便当人工审核）→ 加个封面图 → 预览 → 发布

内联 CSS 会完整保留，粘贴即排版好的成品。

## TODO(学习者)：接管这些关键环节

- [ ] **改信息源**：`config/sources.yaml` 增删你关注的源（比如加 arXiv cs.RO 盯具身智能）
- [ ] **调筛选口味**：`src/curator.py` 里的 `PROMPT`，改价值排序规则和偏好主题
- [ ] **改排版**：`templates/wechat.html`，所有样式都是内联 `style=""`，换配色/字号直接改
- [ ] **自建 RSSHub**（可选）：公共实例不稳时，`docker run -d -p 1200:1200 diygod/rsshub`，然后把 sources.yaml 里的 `rsshub.app` 换成你的地址
- [ ] **加封面图自动化**（可选进阶）：用 ImageGen API 每日生成一张封面

## FAQ

**Q: 为什么不全自动发布？**
微信只对**已认证**的订阅号开放草稿/发布 API，个人主体无法认证。走第三方全自动工具有封号风险。最后人工一步（2 分钟）顺便完成了内容审核，对长期做号是好事。

**Q: 某个 RSS 源一直失败？**
日志里搜 `[FAIL]`。公共 RSSHub 实例不稳定是常态，方案见上面"自建 RSSHub"。

**Q: 周末/节假日条目太少？**
`python -m src.pipeline --window-hours 72`，或在 workflow 里加条件传参。

**Q: 想改成每周精选？**
workflow 里 cron 改成 `0 1 * * 1`（每周一 UTC 01:00 = 北京时间周一 09:00），`--window-hours` 调到 168。
