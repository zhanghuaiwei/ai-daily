# 部署与每日发布手册

> 项目在本沙箱已全流程验证（抓取 → DeepSeek 筛选 → HTML/MD 双产出）。
> 剩下的部署只能在你本机做：沙箱网络隔离了 GitHub，物理不可达。
> 照下面做，全程约 10 分钟，之后每天零成本自动运行。

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
| `LLM_API_KEY` | 你的 DeepSeek key（`sk-` 开头） |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | `deepseek-v4-pro` |

> DeepSeek key 在 [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) 创建。
> 想换回 OpenAI：BASE_URL 填 `https://api.openai.com/v1`、MODEL 填 `gpt-4o-mini`，其余不动。

## 阶段三：手动触发验证（网页，3 分钟）

1. 仓库页 → **Actions** 标签 → 左栏 **AI Daily Digest** → 右侧 **Run workflow** 按钮 → 绿色确认
2. 等运行出现（黄色转圈 → 绿色对勾），点进去看日志：
   - `Run pipeline` 步骤里应出现 `[OK] xxx N 条` 若干、`LLM 筛选出 N 条`
   - `Commit daily output` 步骤应有 `daily: <日期>` 提交
3. 回到代码页，`output/<今天>/` 下出现 `digest.md` + `digest_wechat.html` = 部署成功

**失败排查**：

| 日志现象 | 原因与处理 |
|---|---|
| `Run pipeline` 步骤红，提示缺 key | Secrets 名字拼错了，注意大小写：`LLM_API_KEY` |
| LLM 步骤超时/解析失败降级兜底 | 模型偶发，重跑一次；频繁出现就换 `deepseek-v4-flash`（快） |
| 个别源 `[FAIL]` | 正常（源偶尔抽风会自动跳过）；全失败才需要查网络 |
| 定时任务不触发 | GitHub cron 常态性延迟几分钟到几小时，耐心等或手动 Run |

## 阶段四：每日发布到公众号（每天 2-5 分钟）

1. 打开仓库 `output/<今天>/digest_wechat.html` → 点右上角下载（或本机 `git pull` 后打开本地文件）
2. 浏览器打开 → `Cmd/Ctrl+A` 全选 → `Cmd/Ctrl+C`
3. [mp.weixin.qq.com](https://mp.weixin.qq.com) → 新建图文 → 正文粘贴 `Cmd/Ctrl+V`
4. 通读审核（重点看 AI 摘要是否准确）→ 加封面 → 预览 → 发布

内联 CSS 会完整保留，粘贴即成品排版。MD 版（`digest.md`）可同步发到知乎/掘金/个人博客。

---

## 日常自定义（改完 commit + push 即生效）

- **加/删信息源**：`config/sources.yaml`（例如加 `http://export.arxiv.org/rss/cs.RO` 盯具身智能论文）
- **调筛选口味**：`src/curator.py` 的 `PROMPT`（价值排序 / 偏好主题 / 论文配额）
- **改排版样式**：`templates/wechat.html`（全部内联 style，改配色字号直接编辑）
- **调整抓取时间窗**：`.github/workflows/daily-digest.yml` 里给 pipeline 命令加 `--window-hours 48`
- **改发布时间**：workflow 里 `cron: '30 23 * * *'`（UTC，北京时间 = UTC+8）

## 安全提醒

- `.env`（本地调试用）已被 gitignore，**永远不要**把 key 写进代码或提交记录
- 对话/剪贴板里出现过的 key，用完建议去后台 rotate（重新生成）
