# FinJev MCP

给 MCP Agent 使用的金融研究判断工具。**Agent 查资料，FinJev 调用 Jev 返回结构化判断，再由 Agent 综合生成有来源的自然语言分析。**

```text
Agent 获取金融证据 → FinJev / Jev 判断 → Agent 综合输出
```

提供 7 个工具：筛选与排序搜索结果、评估来源、核验论断、分类金融事件、判断重要性、决定是否继续研究。
FinJev 不自带金融数据检索，也不执行交易。

## 一条命令安装

准备好 [uv](https://docs.astral.sh/uv/getting-started/installation/)、Git 和 Jev API key 文件。安装到 Codex 还需要 Codex CLI。

```sh
uvx --python 3.12 --from "git+https://github.com/Adaozuishuai/FinJev.git@v0.3.0" finjev-install --client codex --key-file /absolute/path/to/apikey
```

把 `/absolute/path/to/apikey` 换成你的 key 文件路径。安装器会安装后端、检查 MCP 连接并注册客户端；保留其他配置，修改已有文件前先备份，只记录 key 文件路径。默认检查不调用 Jev。

安装后重启或重新加载 Agent，按客户端提示批准 MCP。其他客户端只需替换 `--client`：

| 客户端 | 参数值 |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude-code` |
| Claude Desktop | `claude-desktop` |
| Cursor | `cursor` |
| VS Code | `vscode` |
| 其他 MCP Agent | `generic`（导出配置，自行导入） |

具体配置位置、自检和故障处理见 [安装说明](docs/INSTALL.md)。如果已有 FinJev 插件，请与独立 MCP 二选一，避免重复加载。

## 怎么用

向 Agent 提出研究任务，例如：

> 请分析某公司最新财报。先取得原始披露和来源链接，再调用 FinJev 核验关键论断、判断事件重要性，最后用中文说明事实、推断、风险和待确认事项。

Agent 需要自带浏览、搜索或金融数据工具；没有检索工具时，先提供资料。
支持 MCP prompts 的客户端可使用 `financial_research_workflow`。

## 使用边界

- Jev 返回的是辅助判断，不是最终投资决策。保留 `ABSTAIN`（暂不下结论）和 `HUMAN_REVIEW`（需人工复核），数值计算另用代码核对。
- 传入的证据会发送给 Jev 服务；不要提交不允许第三方处理的保密数据。真实模型调用可能计费。
- 标准 MCP 链路和客户端配置生成已测试，但尚未逐一验收所有客户端界面和操作系统。
- 安装成功不代表金融判断已达到生产决策可靠性；开发标注集也不能当作独立 gold benchmark。

## 更多文档

- [安装、自检与客户端配置](docs/INSTALL.md)
- [开发、标注、评测与生产数据测试](docs/DEVELOPMENT.md)
- [架构设计](docs/architecture.md)
