# ai-daily 项目实现分析

> 分析基准：2026-08-27（本轮重构后）；应用线扩展：2026-10-28。

## 1. 项目定位

`ai-daily` 是一条运行在 GitHub Actions 上的全自动中文 AI 日报生产线：每天北京时间 05:50 触发，按两条线路各生成一篇文章——资讯线从 `config/sources.yaml` 的 RSS 中筛选一个未写过的热门 AI 话题，应用线从 `config/sources-application.yaml` 中筛选一个具体 AI 应用/产品/工具话题——各自完成多源调研、中文成稿、去 AI 味处理后，产出 `output/YYYY-MM-DD/article.md` 与 `output/YYYY-MM-DD/application.md`，一起提交到 GitHub 并经 Server酱 推送到个人微信（应用线标题带「AI应用|」前缀）。

## 2. 端到端流程

```text
每条线路独立执行（--edition news / application，信息源不同）：
RSS 并发抓取（fetcher）
  → 全历史来源去重（history，链接池两条线共享）
  → LLM 话题选择，重复时降级为最新 AI 话题（curator，按线路选提示词）
  → 最多 4 个来源原文调研（researcher）
  → 证据包一次成稿、确定性去 AI 味（writer，按线路插内容角度）
  → 公众号 Markdown 渲染，原子写入（renderer，文件名按线路）
  → 一次提交带上 GitHub + 各自推送 Server酱微信（workflow / delivery）
```

模型或抓取完全失败时对应线路失败，不会把资料卡冒充正式文章发送，也不影响另一条线路交付；质量诊断只记录警告，不阻止投递。

## 3. 模块职责

| 模块 | 职责 | 关键机制 |
|---|---|---|
| `src/safety.py` | 不可信数据横切清洗 | 控制字符/HTML 标签剥离、NFC 归一化、HTTP(S) URL 白名单校验、去跟踪参数的 URL 归一化 |
| `src/editions.py` | 线路注册表 | 每条线路的信息源默认路径、产物文件名、微信推送标题前缀；新增线路只改这一处 |
| `src/fetcher.py` | RSS 抓取 | 6 线程并发、20s 超时、指数退避重试、5MiB 上限、单源失败隔离；`download_url` 带私网地址拦截（SSRF 防护） |
| `src/history.py` | 全历史去重 | 链接池扫描两条线路全部往期文章的隐藏来源注释（共享池）；标题史按线路分文件扫描，兼容旧版 `[原文](url)` 链接和旧版 JSON；`load_cross_edition_titles` 提供同日跨线标题 |
| `src/curator.py` | LLM 选题 | GPT → DeepSeek → WorkBuddy → 千问四级故障转移、按线路选用 `TOPIC_PROMPT`/`APPLICATION_TOPIC_PROMPT`、具体性边界校验、进程内熔断、标题相似度防重（0.72 阈值）、候选链接白名单校验 |
| `src/researcher.py` | 原文调研 | 最多 4 源并发抓正文、自研 HTML 正文抽取（忽略 script/nav/footer）、失败回退 RSS 摘要 |
| `src/writer.py` | 一次成稿 | 单次 LLM 调用产出结构化 JSON、按线路插入内容角度段、确定性清洗去 AI 味、标题 A/B 候选、多样化注意力后缀、纯确定性质量诊断 |
| `src/renderer.py` | 排版输出 | 无模板痕迹的公众号 Markdown、临时文件 + `replace` 原子写入、同日重跑清理旧版多文件产物、文件名按线路参数化 |
| `src/delivery.py` | 微信推送 | Server酱 Turbo、推送 day 目录下全部线路文章（逐篇独立尝试，全部失败才报错）、应用文件标题加「AI应用|」前缀、sendkey 格式校验、推送前剥离隐藏注释、错误信息脱敏 |
| `src/pipeline.py` | CLI 入口 | 串联全流程、`--edition news|application`、`--dry-run` 无 LLM 预演、参数校验 |

## 4. 关键设计决策

### 4.1 单一产物原则
每天只生成 `output/YYYY-MM-DD/article.md` 一个文件。历史 Markdown 同时承担两个职责：发布归档 + 去重索引。状态管理极简，没有数据库、没有副作用文件。

### 4.2 LLM 输出零信任
- 选题返回的 `source_links` 必须命中 RSS 候选集合，杜绝模型编造链接；
- 标题、来源等字段最终从 feed 原值回填，不信任模型转写；
- 文章结构（章节数、标题候选数、必填字段）在 `_sanitize_article` 中做确定性校验，不合格直接判为生成失败；
- 所有提示词中显式声明候选数据是内容不是指令（提示词注入防御）。

### 4.3 多供应商故障转移
GPT → DeepSeek → WorkBuddy → 千问，千问固定为最终兜底（配置顺序无法剥夺其兜底语义）。额度类错误（401/402/403/429/5xx、超时、连接错误）触发进程内熔断，避免同一次运行中重复撞墙；非额度类错误（如 JSON 无效）不熔断，只切换到下一家。

### 4.4 双层去重
1. **来源链接层**：`load_recent_links` 收集全部往期文章的来源 URL（含归一化：去 utm/跟踪参数、去尾斜杠），当天候选先排除已用链接；
2. **话题标题层**：`topic_title_is_repeated` 用标题归一化 + `difflib` 相似度（≥0.72）拒绝换标题重写旧话题。

新格式的来源链接放在 `article.md` 末尾的 HTML 注释里（`<!-- ai-daily-sources: ... -->`），渲染时不可见，但 `history.py` 能解析，`delivery.py` 在推送微信前会剥离。

### 4.5 具体选题边界
选题提示词要求每篇文章只围绕“一个具体对象、一个明确变化、一个读者问题”展开，优先产品功能、模型更新、开源项目、论文实验、规则变化和真实事故。`topic_is_too_broad` 会拦截“AI 行业趋势、智能体时代、技术原理综述”等没有明确事件锚点的宏大或理论化话题；兜底选题也会跳过这类候选。

### 4.6 去 AI 味的确定性
两层防线：
- 写作提示词中显式禁止套话、排比、模板化栏目名；
- `_remove_ai_taste` 对 16 个常见 AI 腔短语做确定性删除，质量诊断中 `human_style` 检查兜底。

### 4.7 质量诊断（纯确定性）
`article_metrics` 的 10 项检查全部基于文本本身的确定性计算（篇幅、中文占比、摘要长度、标题 A/B、结构唯一性、注意力钩子等），不再依赖模型自评维度。诊断只记录警告，永不阻断投递——避免了"占位评分导致每天误报警"的噪音问题。

### 4.8 SSRF 防护
`download_url`（调研抓取不可信文章链接的唯一入口）在下载前：
1. 拒绝 `localhost`/`.local` 主机名；
2. DNS 解析后拒绝所有非全局 IP（覆盖回环、私网、链路本地、保留段，含 IPv6）；
3. 自定义重定向处理器对每一跳重定向重复校验，防止公共 URL 302 跳内网。

配置源（`sources.yaml`，可信输入）不走该校验，保留自建 RSSHub（如 `localhost:1200`）的可用性。

### 4.9 双线路（2026-10-28 扩展）

在单一资讯线之上新增应用线，两条线路共用同一套约束（单篇、全历史去重、无质量门禁、失败不产可推送文件），只差三件事，全部收敛在 `src/editions.py` 的注册表里：

| | 资讯线 news | 应用线 application |
|---|---|---|
| 信息源 | `config/sources.yaml`（新闻/热点视角） | `config/sources-application.yaml`（应用/产品/工具视角） |
| 产物 | `output/<日期>/article.md` | `output/<日期>/application.md` |
| 微信标题 | 原标题 | 「AI应用\|」前缀 |

去重语义：链接池两条线共享（同一 URL 全仓库最多用一次）；标题史按线路分开扫描（应用线可以在往日之后换应用角度重写同一事件），但 `load_cross_edition_titles` 会把当天另一条线已写的标题并入候选去重，保证同日不撞题。选题与写作的差异只体现在提示词：`APPLICATION_TOPIC_PROMPT` 只接受"照着做就能复现"的候选——必须带上手细节（步骤、命令、提示词、配置、实测结果），描述性新闻（发布、融资、跑分）直接放弃；`WRITE_PROMPT` 通过 `{edition_angle}` 占位符按线路插入教程结构要求（前置条件 → 分步做法 → "看到什么才算成功" → 适用边界），并声明该结构覆盖共享结构，步骤只能来自证据包、不得虚构。2026-10-29 收紧：应用线从"应用资讯"进一步定位为"可验证、可实践的教程/实践方案"。

## 5. 交付链路

- `daily-digest.yml`：每天 05:50（北京时间）生成两篇 → 提交 GitHub → 各自推送微信；06:30、07:10 两个备用触发应对 GitHub 定时任务高峰期延迟/丢弃（2026-08-28 曾整天未触发）；某条线路当日文章已存在时该线直接跳过，保证幂等；两个生成步骤 `continue-on-error` 互相独立，末尾守门步骤让任一实际执行且失败的线把整个工作流标红；带 `concurrency` 防重入，`timeout-minutes: 60`。
- `retry-delivery.yml`：手动触发，按日期重推该日全部已存在文章到微信（逐篇独立尝试），不重新生成。
- `ci.yml`：push/PR 触发 compileall + ruff + pytest。

## 6. 工程细节备忘

- feedparser 的 `*_parsed` 是 UTC `struct_time`，必须用 `calendar.timegm` 而非 `mktime`（否则 UTC+8 环境下条目"凭空变旧"8 小时）——见 `fetcher._entry_ts`；
- 按源轮询采样（`_sample_items`）避免 arXiv 之类的大源占满 LLM 候选窗口；
- 千问显式关闭 `enable_thinking`，控制单次长文请求时延；
- GPT-5.6 系列 用 `reasoning_effort` 替代 `temperature`，其他供应商保留 `temperature`；
- `_parse_json_content` 仅修复尾逗号这一种无歧义语法错误，绝不猜测缺失字段；
- 所有密钥（API key、sendkey）在日志和异常信息中脱敏。

## 7. 本轮重构记录（2026-08-27）

| # | 变更 | 动机 |
|---|---|---|
| 1 | 删除 `article_metrics` 中依赖 review 维度的检查项及整套 review 占位机制 | 原 review 是固定占位符，导致 `topic_focus`/`logical_flow`/`model_review` 等检查每天确定性误报，淹没真实信号 |
| 2 | `download_url` 增加 SSRF 防护（私网拦截 + 重定向校验） | 调研模块会抓取 RSS/LLM 提供的任意 URL，原 `safe_http_url` 只校验格式不校验目标网段 |
| 3 | 删除旧流程死代码：`curate_with_llm`、`curate_fallback`、`PROMPT`、`_validate_picks`、`sanitize_pick` | 日报精选（3-5 条）是旧版多文章流程遗留，当前管线只用 `plan_topics_*` |
| 4 | 无钩子标题的后缀从单一模板改为 6 候选池，按标题 crc32 稳定选择 | 原来"：为什么这次不一样？"一个模子，本身就是新的 AI 味 |
| 5 | 文章输出去模板化：删除引用标记、参考资料、写在最后、资料整理日期；收尾改为自然段落；来源链接移入隐藏注释（保去重）；写作提示词增加反模板化约束；微信推送前剥离注释 | 最终产物更接近真人公众号排版 |
| 6 | 段落数据结构从 `{"text", "source_ids"}` 简化为纯字符串 | 引用删除后 source_ids 无消费者，但对模型返回对象形态保持兼容 |

## 8. 测试与验证

```bash
python -m compileall -q src tests
ruff check src tests
python -m pytest
```

- 10 个模块 9 个测试文件，共 72 个测试，全部离线可跑（网络边界全部 mock）；
- 覆盖重点：LLM 输出校验与故障转移、SSRF 拦截、新旧两种历史格式的去重、隐藏注释的写入/解析/剥离、原子写入与旧产物清理、双线路的提示词选择/文件名/共享链接池/同日跨线标题/逐篇推送。

## 9. 已知限制

- 全历史去重随归档天数线性增长（一年 365 个文件仍在秒级，暂无优化必要）；
- `_UNAVAILABLE_PROVIDERS` 熔断不恢复，对单次 CLI 运行合理，若改常驻服务需加 TTL；
- SSRF 检查存在理论上的 DNS rebinding 竞态（解析与连接两次 DNS），当前威胁模型下可接受；
- Server酱 是第三方服务，推送正文会经过其中转（README 已声明）；
- 自动生成内容仍应在公开发布前人工事实核验；
- 应用线 18 个源中 Hugging Face 与两个 Reddit 子版本地网络无法直连、未实测，靠 Actions 海外 runner 抓取，失败自动跳过（与资讯线 RSSHub 同类处理）；r/AI_Agents 本地实测触发 429 限流，海外 runner 上频率更低；
- 两条线在同一个 workflow run 中先后生成，LLM 调用量翻倍（选题 + 成稿各 2 次），仍在 60 分钟超时与供应商额度预算内。

## 10. 应用线扩展记录（2026-10-28）

| # | 变更 | 动机 |
|---|---|---|
| 1 | 新增 `src/editions.py` 线路注册表与 `pipeline --edition` 参数 | 把"哪些东西因线路而异"收敛到一处，其余约束两条线共用同一份代码 |
| 2 | 新增 `config/sources-application.yaml`（15 源，12 个实测） | 应用线信息源与资讯线完全不重叠，覆盖一手产品、聚合、产品发现、工具探索、工作流自动化、社区、中文 |
| 3 | 新增 `APPLICATION_TOPIC_PROMPT`，`plan_topics_with_llm` 按线路选提示词 | 应用线选题边界（应用/产品/工具/落地，拒绝融资榜单纯跑分）与资讯线不同，但校验、去重、故障转移全部复用 |
| 4 | `WRITE_PROMPT` 增加 `{edition_angle}` 占位符 | 应用线成稿聚焦"能用它做什么、怎么用起来、对谁有用"，结构与去 AI 味规则共享 |
| 5 | `history.py` 链接池扩展到两线路文件、标题史按线路扫描、新增 `load_cross_edition_titles` | 链接全仓库唯一（共享池）；标题分线允许换角度重写；同日跨线不撞题 |
| 6 | `renderer.write_article_output` 文件名参数化 | 应用线产物 `application.md`，原子写入与旧产物清理逻辑不变 |
| 7 | `delivery.py` 改为逐篇独立推送 day 目录全部线路文章 | 一篇推送失败不拖垮另一篇；全部失败才报错；应用文件标题加「AI应用\|」前缀 |
| 8 | `daily-digest.yml` 双生成步骤（`continue-on-error`）+ 守门步骤 | 两条线互相独立交付，任一执行过的线失败仍让工作流标红，失败可见性不降级 |
| 9 | 应用线收紧为教程/实践方案（2026-10-29）：重写 `APPLICATION_TOPIC_PROMPT` 与 `_EDITION_ANGLE`，新增 LangChain/CrewAI/freeCodeCamp 三个教程型源 | 用户反馈：描述性报道不是要的应用文章；应用篇必须可验证、可实践，照着做能复现 |
