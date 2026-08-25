# OpenAI 自研芯片首批基准:比英伟达 Blackwell 更快更省电,但目前只是自测

> OpenAI 8月25日公布自研推理芯片 Jalapeño 的首批基准,称在 GPT\-OSS 120B、DeepSeek R1 和 Kimi K2\.5 1T 上,每瓦 AI 工作量比对比 Nvidia Blackwell 系统高1\.5至1\.9倍,端到端延迟低1\.7至3\.6倍。该芯片计划2026年底小批量部署、2027年放量。文章拆解这些倍数的含义、局限及其对英伟达依赖的短期影响。

8月25日,OpenAI 在博客和 Hot Chips 上公布了自研推理芯片 Jalapeño 的第一批基准结果。它给出的结论很直接:在 SemiAnalysis 的 InferenceX 平台上,Jalapeño 的每瓦 AI 工作量是对比系统的1\.5至1\.9倍,端到端延迟低1\.7至3\.6倍。一个芯片同时在这两项指标上占优并不常见。不过需要先说明,这些数字来自 OpenAI 自己的测试,对比对象是当时平台上的 Nvidia Blackwell 系统。

## 为什么 OpenAI 要做推理芯片

Jalapeño 是 OpenAI 与 Broadcom 合作开发的 ASIC,定位不是训练模型,而是运行已经训练好的模型,也就是 AI 推理。用户在 ChatGPT 里提问、调用 API 生成回答,都发生在推理阶段。相比训练,推理更在意响应速度和长期运行成本,因此专用芯片有机会在特定负载上做得比通用 GPU 更高效。【1】【2】

对大模型公司来说,推理成本已经变成日常经营里无法绕开的一项。与其全部依赖外部芯片,OpenAI 选择自己做一款推理芯片,目标很明确:在它自己最熟悉的工作负载上,用更少的功耗完成更多回答。

## 基准怎么测,结果好在哪里

这份基准使用 SemiAnalysis 的 InferenceX 平台,覆盖 GPT\-OSS 120B、DeepSeek R1 和 Kimi K2\.5 1T 三个模型。OpenAI 称对比对象是当时 InferenceX 上的最佳结果;The Verge 报道为 Nvidia GB200 或 GB300 superchips,TechCrunch 则概括为 Nvidia Blackwell 系统。【1】【2】

OpenAI 给出的核心结果是:在这三个模型上,Jalapeño 的每瓦 AI 工作量是对比系统的1\.5至1\.9倍,端到端延迟低1\.7至3\.6倍。TechCrunch 进一步显示,Jalapeño 的每用户 token 数和每千瓦吞吐量均高于当时可用的最先进推理处理器。【1】【2】

这两个指标分别对应不同的意义。每瓦 AI 工作量衡量的是同样一度电能完成多少推理,直接影响成本和可承载规模;端到端延迟衡量的是用户发出请求后要等多久才收到响应,直接影响产品体验。低延迟和高吞吐通常不容易同时做到:为了更快响应,系统往往不能把批次塞得太满;为了更高吞吐,又常需要更大批次并增加等待。【1】【2】

Jalapeño 的设计试图绕过这个矛盾。OpenAI 博客称,它的设计重点是最小化数据移动和通信延迟,并让 KV cache 可以显式放置并保持在本地,以优化 prefill 和 communication 阶段。通俗地说,就是减少芯片反复搬运上下文数据,让生成过程更连贯、更省电。【2】

## 短期更像补充,而不是替代

从 OpenAI 公布的节奏看,Jalapeño 不会马上改变其芯片采购。Richard Ho 估计,它会在 2026 年底以非常小批量部署,2027 年放量;OpenAI 没有透露具体芯片数量。【1】【2】

OpenAI 还明确表示,不会用 Jalapeño 完全替换现有芯片阵容,将继续与 Nvidia 等伙伴合作,并开发第二代和第三代 Jalapeño。这个消息可以理解为一种现实判断:自研芯片在量产早期需要时间爬坡,而现有 GPU 仍要承担大量推理请求。【1】

因此,Jalapeño 在 2026 到 2027 年间更可能的角色是补充 OpenAI 的推理能力,而不是直接取代英伟达 GPU。它能证明专用设计可以跑通一部分真实工作负载,但真正影响采购结构,还要看放量后的良率、成本和稳定性。

## 这些数字还没回答的问题

目前最明显的限制是,基准结果来自 OpenAI 自行测试或发布,证据中没有说明是否有 SemiAnalysis 或其他第三方独立验证。没有独立复现,外界很难判断测试条件、软件优化和对比系统选择是否公平。尤其在 AI 芯片领域,测试条件的小差异会明显影响结果。

另一个问题是缺少绝对数值。OpenAI 只给出与对照系统的倍数,没有披露每秒 token 数、绝对功耗、绝对延迟和芯片数量。举例来说,延迟低 1\.7 倍听起来不错,但如果绝对延迟原本不高,或者测试负载比真实服务简单,用户的体感差异可能并没有倍数那么显著。

对比型号也不够明确。The Verge 写的是 Nvidia GB200 或 GB300 superchips,TechCrunch 只写 Nvidia Blackwell 系统。TechCrunch 还提醒,到 Jalapeño 全面部署时,竞争产品可能已经显著进步。换句话说,今天对比的对手,不一定是 2027 年量产时要面对的对手。【1】【2】

## 普通读者可以关注什么

如果你只是希望 ChatGPT 响应更快,这些倍数还不能直接换算成用户体验。OpenAI 没有公布基准对应的真实产品负载,也没有说明 2026 年底小批量部署是否会承接普通用户的请求。更合理的预期是,短期体感变化不会来自这颗芯片。

更值得关注的节点有两个:一是有没有第三方机构独立验证这些结果;二是 2027 年放量时,Jalapeño 与同期的 Nvidia 最新系统直接对比会是什么表现。只看发布首日的倍数,容易高估它的短期冲击。

## 写在最后

Jalapeño 的第一批基准更像一个信号,而不是结论。它说明 OpenAI 有动力、也有能力把推理负载放到更专用的芯片上,并在一组自测指标里取得了领先。但芯片行业的变化通常不以发布会当天为终点,真正值得观察的是量产、独立测试和真实工作负载下的持续表现。在那之前,这颗芯片更像是 OpenAI 对英伟达依赖的一次小幅修正,而不是替代。

## 参考资料

1\. The Verge AI：[原文](<https://www.theverge.com/ai-artificial-intelligence/984290/openai-jalapeno-ai-chip-benchmarks>) · OpenAI says its Jalapeño chip can power faster AI responses than the competition
2\. TechCrunch AI：[原文](<https://techcrunch.com/2026/08/25/openais-jalapeno-chip-is-built-for-fast-inference-at-scale-benchmarks-show/>) · OpenAI’s Jalapeño chip is built for fast inference at scale, benchmarks show

<sub>资料整理日期：2026-08-26。发布前请进行人工事实核验。</sub>