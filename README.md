# ai-daily：每日一篇 AI 热门话题

[![CI](https://github.com/zhanghuaiwei/ai-daily/actions/workflows/ci.yml/badge.svg)](https://github.com/zhanghuaiwei/ai-daily/actions/workflows/ci.yml)

`ai-daily` 每天从多个 AI 信息源中选择一个未写过的热门话题，完成多源调研、中文写作、去 AI 味和公众号 Markdown 排版，将唯一产物提交到 GitHub 并推送到个人微信。

## 固定规则

- 每天只生成一篇文章，唯一产物是 `output/YYYY-MM-DD/article.md`。
- 同一天从旧版流程迁移或重跑时，会移除该日期的旧摘要、JSON、HTML 和 `article-XX` 目录，只保留新的 `article.md`。
- 选题先找未写过、范围具体的 AI 事件：必须能说清“一个对象、一个变化、一个读者问题”；热门事件与往日重复时，降级选择最新的未写 AI 事件。
- 拒绝 AI 行业趋势、智能体时代、大模型竞争、宏观影响、技术原理综述等大而空或纯理论话题；优先产品功能、模型更新、开源项目、论文实验、规则变化和真实事故。
- 去重覆盖仓库内全部往日 Markdown 和旧版文章记录，不因当天候选不足而复用旧来源。
- 标题允许悬念、反差、问句和适度“标题党”，但不得虚构正文没有的事实。
- 写作提示和确定性清洗共同删除常见 AI 套话。
- 质量检查只记录诊断警告，不阻止完整文章写入和微信推送。
- 仅保留 GitHub 和 Server酱微信两个出口；不生成 HTML、JSON、图片，也不发送邮件。
- 仅支持云端 OpenAI 兼容文字接口；拒绝 Ollama、localhost 和默认 Ollama 端口 `11434`。
- GitHub Actions 每天北京时间 05:50 自动执行（06:30、07:10 为备用触发；当日文章已存在时自动跳过，不重复生成和推送）。

## 流程

```text
RSS 抓取
  → 全历史来源去重
  → 热门 AI 话题选择
  → 重复时降级为最新 AI 话题
  → 最多 4 个来源交叉调研
  → 证据包一次成稿、内部终审去 AI 味
  → 公众号 Markdown
  → GitHub 提交
  → Server酱微信推送
```

模型或抓取完全失败时任务会失败，不会把资料卡冒充正式文章发送；只有质量评分不理想时，文章仍会按要求正常推送。

## 快速开始

环境要求：Python 3.11+。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
cp .env.example .env
```

先运行不调用文字模型的结构预演：

```bash
python -m src.pipeline --dry-run --window-hours 72
```

正式生成一篇文章：

```bash
python -m src.pipeline --target-chars 2000
```

本地推送已经生成的 Markdown：

```bash
python -m src.delivery --day-dir output/2026-08-27
```

## 配置

至少配置一个文字模型 Key，并配置微信推送：

| 变量 | 作用 |
|---|---|
| `LLM_PROVIDER_ORDER` | 云端模型顺序，默认 GPT、DeepSeek、WorkBuddy、千问 |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | GPT 或兼容云端接口 |
| `DEEPSEEK_*` | DeepSeek 云端故障转移 |
| `WORKBUDDY_*` | 腾讯云 TokenHub 云端故障转移 |
| `QWEN_*` | 千问最终兜底 |
| `WECHAT_SENDKEY` | Server酱 Turbo 微信推送 |

默认给单次长文模型请求 300 秒，并关闭 SDK 内部重复等待；供应商额度不足或未授权后会在本次运行中熔断。选题后只发起一次必需的成稿请求，千问关闭长思考模式，避免多阶段调用拖垮每日任务。

本地配置写入 `.env`；GitHub 配置写入仓库 Actions Secrets。完整步骤见 [DEPLOY.md](./DEPLOY.md)。

## Markdown 排版

最终文件是一篇干净的公众号文章，不带模板化栏目：

- 一个有注意力钩子的一级标题；
- 导读引用块；
- 4–8 个短小、职责明确的章节；
- 自然的收束段落（没有“写在最后”“结语”这类栏目名）；
- 没有引用编号、参考资料和资料整理日期；
- 文末隐藏的 HTML 来源注释只用于历史去重，渲染时不可见，微信推送前会被剥离。

## 选题口径

每篇文章只处理一件具体的事，优先采用“一个具体对象 + 一个明确动作/变化 + 一个实际影响”的结构。文章不尝试概括整个行业或技术发展史，最多解释一个读者必须知道的核心概念，并用工作、上网、手机或日常生活中的场景说明它为什么值得关注。

## 历史去重

项目永久保留每日 Markdown，因为它们同时承担发布归档和去重索引。每次运行会读取：

- 新格式 `output/*/article.md`（来源链接在文末隐藏注释里）；
- 旧格式 `output/*/article-*/article.md`（来源链接在“参考资料”里）；
- 旧版 JSON 中的来源和标题，仅用于兼容已有历史。

如果所有候选来源都已经出现过，任务会停止，不会重复发布。

## 开发验证

```bash
python -m compileall -q src tests
ruff check src tests
python -m pytest
```

## 项目结构

```text
src/
├── safety.py        # 不可信数据清洗和 URL 校验（横切层）
├── fetcher.py       # RSS 并发抓取、SSRF 防护
├── curator.py       # 热门选题、最新降级、多模型故障转移
├── history.py       # 全历史链接和标题去重
├── researcher.py    # 原文调研
├── writer.py        # 写作、去 AI 味、标题和诊断
├── renderer.py      # 单篇 Markdown 排版
├── delivery.py      # Server酱微信推送
└── pipeline.py      # 每日单篇入口
```

实现细节分析见 [ANALYSIS.md](./ANALYSIS.md)。

## 安全说明

- `.env` 和所有真实密钥不得提交。
- 微信推送正文会经过 Server酱第三方服务。
- RSS、网页正文和模型输出都按不可信数据处理。
- 调研抓取的不可信 URL 会拒绝内网、回环和保留地址（含重定向跳转）。
- 自动生成内容仍应在公开发布前进行人工事实核验。

MIT License。
