# GitHub 自动生成与微信推送

项目每天北京时间 05:50 生成两篇文章——资讯线 `article.md` 和应用线 `application.md`，一起提交到当前 GitHub 分支后，各自通过 Server酱推送到个人微信（应用线标题带「AI应用|」前缀）。两条线路互相独立：一条失败不拖垮另一条，但任一执行过的线失败会让工作流标红。

## 1. 配置 Actions Secrets

仓库进入 **Settings → Secrets and variables → Actions**。

至少配置一个云端文字模型 Key：

- `LLM_API_KEY`，可选 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_REASONING_EFFORT`；
- 或 `DEEPSEEK_API_KEY`；
- 或 `WORKBUDDY_API_KEY`；
- 或 `QWEN_API_KEY`。

再配置：

- `WECHAT_SENDKEY`：Server酱 Turbo SendKey。

可在 Actions Variables 中配置 `LLM_PROVIDER_ORDER`。项目只接受云端 OpenAI 兼容接口，不支持 Ollama、本机地址或端口 `11434`。

## 2. 手动验证

1. 打开 **Actions → AI Daily Markdown**。
2. 选择 **Run workflow**。
3. 确认 `Generate news article` 和 `Generate application article` 都成功（某条线路当日文章已存在时该步会跳过）。
4. 仓库出现 `output/<北京时间日期>/article.md` 和 `output/<北京时间日期>/application.md`。
5. `Push Markdown to WeChat` 成功，个人微信收到两篇 Markdown 文章，应用线标题以「AI应用|」开头。

若当天某条线路已经被旧版流程生成过，首次新流程运行会清除该日期旧的多文件产物，只留下新的 `article.md`；往日日期不会被改动。

流水线不会因为质量诊断分数较低而跳过投递；抓取失败、模型无法生成完整文章、Markdown 缺失或微信接口失败仍会让对应线路（进而整个工作流）失败。

## 3. 定时规则

工作流使用：

```yaml
schedule:
  - cron: '50 5 * * *'
    timezone: 'Asia/Shanghai'
```

即每天北京时间 05:50。GitHub 调度可能有少量排队延迟。

## 4. 重试微信

文章已提交但微信临时失败时，打开 **Retry Existing WeChat Delivery**，填写 `YYYY-MM-DD`。重试会推送该日期目录下全部已存在的文章（`article.md` 和 `application.md`，逐篇独立尝试），不会重新生成文章。

## 5. 常见失败

| 现象 | 处理 |
|---|---|
| 未配置文字模型 Key | 至少配置一个云端供应商 Key |
| 本地/Ollama 地址被拒绝 | 改用供应商 HTTPS 云端兼容接口 |
| 所有候选都曾使用 | 该线路停止并让工作流标红；扩大 `--window-hours` 或增加新信息源，不会强行重复 |
| 一条线失败、另一条成功 | 成功的一篇照常提交并推送；工作流标红提示失败的那条，可手动 Run workflow 只补生成缺失线路 |
| 质量诊断不理想 | 仍继续生成 Markdown 并投递，不设置质量门禁 |
| 模型无法生成完整文章 | 对应线路失败，不推送资料卡或残缺内容 |
| `WECHAT_SENDKEY` 无效 | 在 Server酱重新生成并更新 Secret |
| 当日 Markdown 不存在 | 先修复生成步骤，再执行微信重试 |

## 6. 本地测试

```bash
python -m compileall -q src tests
ruff check src tests
python -m pytest
python -m src.pipeline --dry-run --window-hours 72
python -m src.pipeline --edition application --dry-run --window-hours 72
```
