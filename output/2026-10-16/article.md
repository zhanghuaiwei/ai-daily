# 816B参数的开源模型，两台Mac Studio就能跑，被忽略了什么？

> **导读**｜Meta发布开源权重模型Muse Spark Open，总参数达816B。通过MoE架构和苹果的MLX框架，该模型首次实现同类规模在两台M5 Ultra Mac Studio上本地运行，支持文本、图像、视频和音频处理。

---

10月15日，Meta发布了开源权重模型Muse Spark Open，并宣布它可以在两台搭载M5 Ultra芯片的Mac Studio上本地运行。对于习惯租用云端算力或购买专业显卡来跑大模型的开发者来说，这意味着一种原本需要机房级硬件才能支撑的计算量，现在被压缩到了两张办公桌拼起来的设备里。

## 发生了什么

Muse Spark Open是一个原生多模态模型，能同时处理文本、图像、视频和音频。它的上下文窗口达到100万token。根据Meta公开的信息，这是目前美国能力最强的开源权重模型。

真正引发讨论的是它的运行方式。Meta称，这是同级别模型中第一个能通过苹果最新的MLX框架，直接在桌面上运行的版本。具体的硬件要求是两台配备M5 Ultra芯片的Mac Studio。

为了促成这件事，平时在多个领域存在竞争关系的Meta和苹果进行了数月的合作。Meta CEO扎克伯格和苹果新任CEO John Ternus在社交平台上公开互相致谢。Meta首席AI官Alexandr Wang甚至对媒体开玩笑说，很高兴看到两家公司“又好好相处了”。

## 为什么跟读者有关

理解这件事的关键在于一个概念：混合专家架构（MoE）。你可以把它想象成一家拥有几百名员工的大公司，虽然总共养了816个人（总参数），但每次接到具体任务时，只有最懂行的42个人（激活参数）会去处理。剩下的员工处于待命状态。这让模型既保留了庞大知识库带来的能力上限，又把单次计算的实际工作量降到了一个可控的范围。

即便如此，42B的激活参数加上庞大的模型体积，依然需要极高的内存。苹果的统一内存架构在这里起到了决定性作用。每台M5 Ultra Mac Studio的集成GPU最多可以使用512GB内存，两台机器加起来刚好能装下整个模型。同时，芯片每秒1\.2TB的内存带宽足以快速读取每个词元所需的数据切片。结果就是，两台Mac Studio连在一起，表现得像一台拥有一TB统一内存的小型超级计算机。

Meta展示了一些完全在本地设备上运行的工作流测试。比如配合其编程终端Muse Code，直接为一个开源的Mastodon客户端修复Bug、开发新功能并完成完整构建；或者驱动专业视频剪辑软件DaVinci Resolve，让模型逐帧检查素材，挑出最佳片段并进行垂直裁剪。这些测试表明，它不再只是一个用来对话的聊天机器人，而是开始介入复杂的桌面生产力流程。

## 现在能做什么

Muse Spark Open的模型权重已经开放下载，托管在Hugging Face、Amazon SageMaker AI、Google Cloud Model Garden和Microsoft Foundry Models等平台。如果你不想或无法在本地部署，也可以通过Baseten、Fireworks AI、Groq、Modal、Nebius、OpenRouter和Together AI等API平台直接调用。

它支持目前主流的推理引擎，包括SGLang、vLLM、TensorRT\-LLM、llama\.cpp等，并针对AMD、Apple、Intel和NVIDIA的芯片做了优化。在SGLang中，Meta还加入了定制的Helion GPU核心，官方数据显示这在NVIDIA和AMD GPU上带来了1\.03到3\.95倍的核心级加速。开发者也可以使用PyTorch框架对其进行进一步的定制微调。

需要注意的是，这是一个开源权重模型，采用的是附带有限商业条款的Muse Model License，允许许多开发者免费使用，但并非毫无限制。此外，Meta表示已按照其内部的超级智能扩展框架对该模型进行了安全评估和额外的安全后训练，详细的评估报告将在稍后公布。

---

两台顶配Mac Studio的价格依然远超普通消费级电脑，这暂时还不是一个能让所有人立刻在笔记本上跑起来的玩具。但它证明了一条路径：当模型架构的设计方向与特定硬件的底层特性咬合在一起时，原本属于数据中心的庞然大物，确实可以被搬进个人的书房。

<!-- ai-daily-sources:
  https://research.meta.ai/blog/muse-spark-open
  https://www.theverge.com/news/1012293/meta-apple-muse-spark-open-ai-model-mlx
  https://techcrunch.com/2026/10/15/meta-launches-an-open-weight-model-that-runs-on-macs/
  https://www.reddit.com/r/LocalLLaMA/comments/1x6r9pz/introducing_muse_spark_open_the_most_capable_us/
-->
