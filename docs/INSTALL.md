# 一条命令安装 FinJev MCP

FinJev v0.3.0 是标准 **stdio MCP**，不是只能由 Codex 安装的专有插件。
使用同一套七个业务工具和 `financial_research_workflow` MCP prompt。

## 安装

前提：已安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Git，能访问 GitHub/Python 包索引，已有 Jev key 文件。
不需要自行 clone 仓库、不需要手动创建虚拟环境、不修改系统 Python。
uv 按需提供 Python 3.12。首次下载依赖需要联网；研究时 Jev 也需要联网。

已有 Codex CLI 时，运行：

```sh
uvx --python 3.12 --from "git+https://github.com/Adaozuishuai/FinJev.git@v0.3.0" finjev-install --client codex --key-file /absolute/path/to/apikey
```

替换 key 文件路径，不要将 key 内容放到命令行。
安装器安装持久化的 `finjev-mcp` 程序，验证 MCP 握手、七个工具及 workflow prompt，
再注册客户端；写入的是程序绝对路径和 key 文件路径。启动不依赖 GUI 的 shell PATH。
这个默认检查**不调用 Jev，也不验证 key 的有效性、余额或网络 API 可用性**。

| 客户端 | 把上面 `--client` 改为 | 注册位置 |
| --- | --- | --- |
| Codex | `codex` | 通过已安装的 `codex mcp add` CLI 注册当前配置 |
| Claude Code | `claude-code` | 用户级 `~/.claude.json` 的 `mcpServers` |
| Claude Desktop | `claude-desktop` | macOS/Windows 的 `claude_desktop_config.json` |
| Cursor | `cursor` | 用户级 `~/.cursor/mcp.json` |
| VS Code | `vscode` | 当前项目 `.vscode/mcp.json` 的 `servers` |
| 其他 MCP Agent | `generic` | stdout 输出通用 `mcpServers` JSON，自行导入客户端 |

VS Code 可加 `--project-dir /absolute/project` 明确指定工作区。
JSON 客户端可加 `--config /absolute/config.json` 指定位置。
Claude Code 自定义配置目录时用 `--config` 指向实际文件，安装器不猜测非默认路径。
通用模式可加 `--output /absolute/finjev-mcp.json` 保存配置。
如果 Codex 只有桌面应用、没有 CLI，使用 `generic` 导出，再按客户端支持的方式导入。

安装后重启/重新加载 Agent；部分客户端还要求信任工作区或批准 MCP。
直接修改 JSON 配置的客户端建议先退出，以免客户端同时保存配置覆盖安装结果。
配置格式适配和标准 MCP 握手已经测试；**并不表示每种客户端/操作系统都做过真实界面验收**。
如果之前已经安装了本地 Codex FinJev 插件，不要同时重复添加同一 MCP：选用插件或独立 MCP 之一。
安装器不会擅自卸载原插件。

## 配置安全与重装

- 保留其他 MCP server 及配置字段，只更新名为 `finjev` 的条目。
- 修改已有文件前创建权限为 `0600` 的随机备份；JSON 配置用原子替换。
- 相同 JSON 配置不重复写入。Codex 由原生 CLI 管理 TOML，写后核对注册结果。
- 遇到损坏 JSON、JSONC 注释配置、错误结构或符号链接配置会拒绝修改。
  VS Code JSONC 请先自行转换为合法 JSON，或用 `generic` 输出后通过客户端界面添加。
- `--dry-run` 仅展示计划，不安装后端、不修改配置。
- key 只从本地文件读取，安装器不复制它、不上传它、不将内容写入客户端配置。
  Jev 请求当然会使用该凭证向服务提供方认证。
- 客户端配置中的 `TYPESAFE_API_KEY` 为空，避免旧 shell key 覆盖选定文件。
- 建议自行将 key 文件权限设为仅当前用户可读（macOS/Linux：`chmod 600 /absolute/path/to/apikey`）。
- 同一用户的客户端共用持久化 FinJev tool 环境；重装会更新这个环境，而不是并行保留多版本。
- 固定 tag 使 FinJev 源码可追踪，但传递依赖仍按 pyproject 版本区间解析，不等于全部依赖哈希锁定。

新版本发布后，将命令中的 tag 替换为新 tag 再运行。
目前从 GitHub 安装，**未发布到 PyPI**，不要使用未经核验的 `pip install finjev`。

## 自检与真实 Jev 检查

安装后，若 uv 的 tool bin 已在 PATH：

```sh
finjev-doctor --key-file /absolute/path/to/apikey
```

显式进行一次**可能计费**的 Jev 调用（使用虚构公司协议测试样例）：

```sh
finjev-doctor --key-file /absolute/path/to/apikey --live
```

如果命令不在 PATH，先按 uv 提示设置 PATH，或使用安装结果中的程序路径。
失败时安装器返回非零退出码，不声称成功；模型调用失败不能以模拟结果代替。
通用 MCP 握手成功与客户端已加载、实际模型调用成功是三个不同验收层级。

v0.3.0 的本地验收（2026-09-29，macOS）：56 项测试通过，Ruff 通过，wheel/sdist 构建通过；
wheel 在独立 uv tool 目录安装、通用 JSON 导出、真实 stdio 工具和 prompt 发现通过。
一次显式 Jev smoke 返回 HTTP 200、`jev-1.13.0`、`HUMAN_REVIEW`、`advisory_only`。
Codex 注册命令做了 dry-run 与模拟原生 CLI 的保存/核对测试；没有改写原来已安装插件的用户配置。
其他客户端配置格式做了自动化测试，但没有逐一验证实际 GUI 加载。
这些结果证明安装和调用链路，不是金融判断准确率或真实交易安全的证明。

## 使用方式与数据边界

向 Agent 说：

> 请研究某公司最新财报。先用你的浏览/金融数据工具取得原始披露和链接，
> 然后调用 FinJev 核验关键论断、判断事件重要性；最后由你写中文分析，
> 明确区分事实、推断、未知项，并保留 ABSTAIN/HUMAN_REVIEW。

支持 MCP prompts 的客户端可以调用 `financial_research_workflow`，参数 `question`、`language`。
服务端初始化也带有研究流程 instructions；是否采用 prompt/instructions 由宿主 Agent 决定。
FinJev **不自带金融数据检索接口**，无数据工具的 Agent 必须先提供证据。
不得把这次安装封装等同于已经获得直接用于交易决策的可靠性证明。

## 客户端配置依据

- Codex：以本机 `codex mcp add --help` 为准。
- [Claude Code MCP](https://code.claude.com/docs/en/mcp)
- [Claude Desktop 本地 MCP](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
- [Cursor MCP](https://prod.cursor.com/help/customization/mcp)
- [VS Code MCP 配置](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
