# KY-TASK Controller

[English](README.en.md) · [MIT License](LICENSE)

KY-TASK 是一个面向 Codex Desktop 的复杂任务总控插件。它先锁定任务边界，再把可以独立推进的工作拆成带依赖关系的 lanes，并优先交给项目内可见的 Codex Session 并行执行，最后统一收口和验收。

它要解决的不是“多开几个 Agent”，而是复杂任务经常出现的四类问题：所有环节挤在同一上下文里、明明可以并行却被串行执行、多个执行者争写同一交付物，以及执行结束后无人进行独立验收。

## 核心能力

- 任务契约：先明确目标、材料、边界、非目标、交付物和验收标准。
- 项目内多 Session：分布式任务使用侧边栏可见的原生 Codex Session，不静默降级为 Sub Agent。
- 依赖驱动并行：一次派发所有已满足依赖的 lanes，默认最多并行 4 个。
- 项目归属保护：worker Session 必须归属同一个已解析的 Codex 项目；无法唯一判断时停止询问。
- 写入边界：并行 lanes 不得争写同一个持久化目标。
- 回调与验收：worker 必须向总控回传结构化结果，review 与 implementation 分离。
- 可扩展能力注册：可以把文档、表格、PPT、飞书或代码能力接入任务图。

## 安全默认值

公开版不携带作者的个人授权、账号、项目路径或会话记录。

插件默认采用 `native_session_required` 与 `inherit_or_resolve_required`：当用户明确批准分布式执行后，KY-TASK 才能为该任务记录 `nativeThreadUserApproved: true` 并创建项目内 Session。未获批准、无法解析项目或原生 Session 工具不可用时，执行会停止，不会悄悄改用 Sub Agent 或创建项目外会话。

## 安装

需要较新的 Codex Desktop，并确保应用内置的 Codex 支持 `plugin` 命令。

### macOS 一键安装

```bash
git clone https://github.com/zhongky1995/ky-task-controller.git
cd ky-task-controller
./INSTALL.command
```

如果系统拦截脚本，可以右键 `INSTALL.command` 后选择“打开”，或者使用下面的手动命令。

### 手动安装

```bash
git clone https://github.com/zhongky1995/ky-task-controller.git
cd ky-task-controller
"/Applications/ChatGPT.app/Contents/Resources/codex" plugin marketplace add "$PWD"
"/Applications/ChatGPT.app/Contents/Resources/codex" plugin add task-controller@ky-task-controller
```

安装后请新建一个 Codex 任务，旧任务不会热刷新插件。

## 使用

直接告诉 Codex：

```text
用 KY-TASK 推进这个复杂任务。先锁定任务边界，再按项目内多 Session 并行执行，最后独立验收。
```

如果只是一个解释题、单文件小修改或低歧义任务，KY-TASK 可以判定为直接执行；多 Session 是复杂任务的执行策略，不是所有请求的固定仪式。

## 运行模型

```text
KY-TASK00 总控
├── KY-TASK01 研究 lane ─────┐
├── KY-TASK02 数据 lane ─────┼─> 综合 / 实施 lane ─> 独立验收 lane ─> 最终交付
└── KY-TASK03 体验 lane ─────┘
```

只有依赖已经满足、且写入目标不冲突的 lanes 才会同时执行。长期工作台可以使用可恢复 Session；一次性研究则使用只接收窄任务包的独立 Session。

## 开发与测试

```bash
cd plugins/task-controller
python3 -m pytest -q
node --check mcp/server.mjs
```

插件结构校验：

```bash
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/task-controller
```

贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请遵循 [SECURITY.md](SECURITY.md)，不要在公开 Issue 中提交凭证或客户材料。

## 许可证

[MIT](LICENSE)
