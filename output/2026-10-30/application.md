# 给 AI 配一个浏览器需要几步？Managed Deep Agents v0\.10 实操

> **导读**｜LangChain Managed Deep Agents v0\.10 新增了浏览器控制能力。本文拆解如何在项目根目录声明浏览器、处理登录交接，以及配置异步子代理在后台并行执行长任务。跟着步骤操作，你可以复现一个能自主浏览网页并填表的 Agent。

---

订机票、退订阅、填报销单——这些每天要在网页上点来点去的事，通常没有 API 可以调用。LangChain 的 Managed Deep Agents 在 v0\.10 版本中加入了浏览器控制能力，让 AI 可以直接像人一样操作网页；遇到需要你输入密码的登录页面，它还会把浏览器窗口交还给你手动完成。这篇教程将带你从零配置并跑通这个流程。

## 前置条件与核心概念

你需要一个 LangSmith 账号，因为 Managed Deep Agents 会在 LangSmith 的沙盒里运行浏览器和 Agent，不需要你在本地搭建任何基础设施。官方信息未披露该功能的具体计费标准，但在一项包含 100 个真实网站任务的基准测试中，总花费为 1\.98 美元。

这里需要理解一个核心概念：无障碍树（accessibility tree）。Agent 并不是像人一样“看”网页上的像素，而是读取浏览器生成的无障碍树——这就像一份网页的结构化大纲，上面每个可点击的按钮、可输入的文本框都会被分配一个 ID。Agent 通过调用这些 ID 来完成点击和填写，而不是识别图像。

## 第一步：在项目根目录声明浏览器

在你的项目根目录下创建一个名为 \`browser\.py\` 的文件，写入以下代码：

\`\`\`python \# browser\.py from managed\_deepagents import define\_browser browser = define\_browser\(scope="thread", idle\_ttl\_seconds=600\) \`\`\`

这段代码告诉系统为当前对话线程启动一个独立的浏览器实例。参数 \`scope="thread"\` 表示每次新对话都会得到一个干净的浏览器，不带有任何历史 Cookie 或登录状态。如果你希望同一个用户在不同对话间共享登录状态（比如只登录一次，后续对话直接用），可以将参数改为 \`scope="user"\`。\`idle\_ttl\_seconds=600\` 意味着浏览器闲置 10 分钟后会自动关闭以节省资源。

保存文件后，系统会自动为你的 Agent 挂载四个工具：\`browser\_snapshot\`（读取无障碍树并分配 ID）、\`browser\_run\`（通过 JavaScript 或动作批次与页面交互）、\`browser\_screenshot\`（截图）和 \`browser\_handoff\`（交出控制权）。看到这四个工具出现在你的 Agent 工具列表中，即代表配置成功。

## 第二步：处理登录交接（Handoff）

第三步：配置异步子代理处理长任务

如果你的 Agent 需要执行耗时较长的任务（比如后台调研），同时你还想继续和它对话，可以使用异步子代理。在定义子代理时加入 \`"async": True\` 参数：

\`\`\`python from managed\_deepagents import define\_deep\_agent agent = define\_deep\_agent\( name="research\-assistant", model="openai:gpt\-5\.5", "name": "researcher", "description": "Researches a topic in the background\.", "system\_prompt": "Research the topic and report your findings\.", "async": True, \) \`\`\`

配置完成后，主 Agent 可以在自己的线程中启动这个子代理去后台工作，而主 Agent 继续响应你的消息。子代理完成后会主动通知主 Agent，不需要轮询等待。如果主 Agent 当时正忙，结果会在下一次模型调用前被处理；如果主 Agent 处于空闲状态，子代理会唤醒它开启新一轮运行。子代理共享主 Agent 的沙盒，因此可以直接读取主 Agent 已经写入的文件。当你向主 Agent 提问并得到即时回复，同时后台任务结束后结果自动追加到对话中，就说明异步机制生效了。

## 验证最终结果

完整的验证路径是：通过对话框指示 Agent 访问一个没有 API 的网站（例如某个预订页面），观察它是否通过 \`browser\_snapshot\` 获取了页面元素并用 \`browser\_run\` 进行了点击或填写；在触发登录时，确认界面是否弹出了交接链接；手动登录交还后，确认 Agent 是否继续完成了后续步骤。在 WebVoyager 基准测试的 100 个日常网页任务中，这套工具的通过率为 90%。

---

这套方案适合需要在无 API 网站上执行自动化操作的开发者，或者需要让代码 Agent 打开浏览器验证前端修改是否生效的团队。如果你要操作的网站有完善的 API，直接调用 API 依然是更稳定、成本更低的选择，没必要动用浏览器。另外，官方文档尚未详细说明如何在非官方支持的自定义客户端中完整渲染交接界面，这部分可能需要根据底层协议自行摸索。下一步，你可以尝试将 \`scope\` 切换为 \`"user"\`，体验跨会话保持登录状态的连贯工作流。

<!-- ai-daily-sources:
  https://www.langchain.com/blog/managed-deep-agents-browser-use-and-asynchronous-subagents
  https://www.langchain.com/blog/browser-use-in-managed-deep-agents
-->
