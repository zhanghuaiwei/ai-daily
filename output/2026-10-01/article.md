# Google 给自家最强 AI 上了锁，只允许“可信防御者”打开：没那么简单

> **导读**｜9月30日，Google 发布了新模型 Gemini 4 Argon。它在编程和网络安全上表现极强，甚至能自主修补软件漏洞，但 Google 没有全面开放，而是仅限经过审核的安全人员使用。

---

9月30日，Google 发布了最新 AI 模型 Gemini 4 Argon。这个模型在编程和网络安全任务上达到了前沿水平，但普通用户和开发者现在都用不了——它目前只开放给经过审核的“可信网络防御者”。如果你关心 AI 工具什么时候能帮你写代码或查资料，这次发布意味着最顶级的模型正在改变分发规则。

## 一个能自己找漏洞的模型

根据 DeepMind 官方博客，Gemini 4 Argon 被训练得高度擅长网络安全防御。它能自主发现、验证并修补关键的软件漏洞。TechCrunch 的报道也确认了这一点，指出网络安全是该模型被特别强调的优势领域。

除了安全，Argon 在软件工程上的测试成绩也很高。在一个衡量真实世界长周期软件工程任务的基准测试 DeepSWE v1\.1 中，它拿到了 77\.9% 的分数。在金融研究、法律文书起草等知识工作测试中，官方给出的对比图表显示其得分高于 OpenAI 和 Anthropic 的同类模型。

支撑这些复杂任务的一个核心变化是输出上限。Argon 将单次输出的 token 数量从之前的 6\.4 万个提升到了 100 万个。Token 可以理解为 AI 处理文本时的基本单位，大致相当于几个汉字或一个英文单词。100 万个 token 的上限意味着模型可以在一次任务中生成极长的内容，不需要中途打断，这让它能一口气处理过去需要分步完成的庞大工程。

## 为什么不给所有人用

以往 AI 公司发布新模型，通常会尽快向开发者和公众开放以抢占市场。但这次，DeepMind 高级副总裁 Koray Kavukcuoglu 在博客中明确表示，安全地发布这种级别的能力需要分阶段进行。

Argon 目前仅通过一个叫 Fairwind Program 的安全项目，提供给一部分可信的网络防御者。同时，Google 正在参与美国政府针对预发布模型的自愿审查流程。The Verge 的报道提到，在更大范围推出之前，Google 计划加强防范滥用和提示词注入攻击的措施，并监控模型是否出现偏离预期的行为。

公开信息没有提到具体的全面开放时间表，博客中的表述是“尽快（as soon as possible）”。Hacker News 社区对这一决定讨论热烈，相关帖子获得了超过 900 分和 600 多条留言。

从分析的角度看，一家公司主动给自己的最强产品加上访问锁，说明当 AI 具备自主寻找并利用系统漏洞的能力时，不受控的扩散风险已经大到必须优先于商业推广。

---

对于开发者或企业用户，如果未来能通过 API 调用 Argon，官方公布的初始定价为每百万输入 token 2 美元，每百万输出 token 10 美元，缓存过的输入价格再打九五折。至于普通用户何时能在日常产品中用上这个模型，目前只能等待 Google 完成安全测试后的下一步通知。

<!-- ai-daily-sources:
  https://deepmind.google/blog/gemini-4-argon-our-next-era-of-frontier-intelligence/
  https://techcrunch.com/2026/09/30/google-releases-gemini-4-argon-called-its-most-powerful-model-yet/
  https://www.theverge.com/tech/1002980/google-gemini-4-argon
  https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/
-->
