# 客户端配置指南 — Claude Code & Codex CLI

本文档说明如何将 Claude Code 和 Codex CLI 配置为使用 eucalAI router-service 作为后端。

---

## 前置条件

- router-service 已启动并可访问（默认端口 8003）
- 已有有效的 API Key（通过 user-service 创建）
- 如果是远程服务器，需要做端口转发（见下方说明）

---

## 端口转发（远程服务器场景）

如果 router-service 运行在远程服务器（如 AutoDL），需要将端口转发到本地。

### 方式一：VSCode Remote SSH（推荐）

1. VSCode 已通过 Remote SSH 连接到远程服务器
2. 按 `Ctrl+Shift+P` → 输入 "Forward a Port" → 输入 `8003`
3. 或在底部 "PORTS" 面板中添加

> 注：如果端口不显示绿色但能正常访问，是因为根路径返回 404，不影响使用。

### 方式二：SSH 隧道

```bash
ssh -L 8003:localhost:8003 -p <SSH端口> root@<服务器地址>
```

转发成功后，本地 `http://localhost:8003` 即可访问 router-service。

---

## Claude Code CLI 配置

Claude Code 使用 Anthropic Messages API (`/v1/messages`)。

### 环境变量

```bash
export ANTHROPIC_BASE_URL=http://localhost:8003
export ANTHROPIC_API_KEY=sk-your-api-key-here
```

### 持久化配置

写入 shell 配置文件（`~/.bashrc` 或 `~/.zshrc`）：

```bash
echo 'export ANTHROPIC_BASE_URL=http://localhost:8003' >> ~/.bashrc
echo 'export ANTHROPIC_API_KEY=sk-your-api-key-here' >> ~/.bashrc
source ~/.bashrc
```

### 验证

```bash
claude "say hello"
```

如果正常返回响应，说明配置成功。

### 模型选择

- 使用 `auto` 作为模型名，router-service 会根据任务难度自动路由到合适的模型
- 也可以在 Claude Code 设置中指定模型名（需要 router-service 配置中支持）

---

## Codex CLI 配置

Codex 使用 OpenAI Responses API (`/v1/responses`)。

### 环境变量

```bash
export OPENAI_BASE_URL=http://localhost:8003/v1
export OPENAI_API_KEY=sk-your-api-key-here
```

### 持久化配置

```bash
echo 'export OPENAI_BASE_URL=http://localhost:8003/v1' >> ~/.bashrc
echo 'export OPENAI_API_KEY=sk-your-api-key-here' >> ~/.bashrc
source ~/.bashrc
```

### 验证

```bash
codex "list files in current directory"
```

### 注意事项

- Codex 默认使用 streaming 模式
- 模型名使用 `auto`，由 router-service 自动路由
- 如果遇到 "stream disconnected" 错误，检查网络连接和端口转发是否稳定
- 长任务（大文件编辑等）可能需要较长时间，streaming 超时已设为 300s

---

## 同时使用两个工具

如果需要在同一终端同时使用 Claude Code 和 Codex，两者的环境变量互不冲突：

```bash
# Claude Code 使用 Anthropic 协议
export ANTHROPIC_BASE_URL=http://localhost:8003
export ANTHROPIC_API_KEY=sk-your-api-key-here

# Codex 使用 OpenAI 协议
export OPENAI_BASE_URL=http://localhost:8003/v1
export OPENAI_API_KEY=sk-your-api-key-here
```

两者可以使用同一个 API Key（router-service 统一鉴权）。

---

## 快速切换脚本

创建一个切换脚本 `~/.eucalai-env.sh`：

```bash
#!/bin/bash
# eucalAI router-service 客户端配置
# source ~/.eucalai-env.sh

export ANTHROPIC_BASE_URL=http://localhost:8003
export ANTHROPIC_API_KEY=sk-your-api-key-here

export OPENAI_BASE_URL=http://localhost:8003/v1
export OPENAI_API_KEY=sk-your-api-key-here

echo "eucalAI 环境已加载 (router: localhost:8003)"
```

使用：
```bash
source ~/.eucalai-env.sh
```

---

## 故障排查

| 问题 | 可能原因 | 解决方案 |
|------|---------|---------|
| `connection refused` | 端口转发未建立或 router-service 未启动 | 检查 `ss -tlnp \| grep 8003` |
| `missing api key` | 未设置环境变量或 key 无效 | 检查 `echo $ANTHROPIC_API_KEY` |
| `insufficient balance` | 账户余额不足 | 通过 admin-service 充值 |
| `model not allowed` | 请求了不支持的模型名 | 使用 `auto` 或检查 runtime_config.json |
| `stream disconnected` | 上游超时或网络不稳定 | 检查上游 API Key 是否有效、网络是否稳定 |
| `upstream service error` (502) | 上游 LLM 服务不可用 | 检查 runtime_config.json 中的 API Key 和 api_base |

### 检查服务状态

```bash
# 检查 router-service 是否响应
curl http://localhost:8003/v1/models -H "Authorization: Bearer YOUR_KEY"

# 测试 Anthropic 协议
curl -X POST http://localhost:8003/v1/messages \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","max_tokens":50,"messages":[{"role":"user","content":"hi"}]}'

# 测试 Responses 协议
curl -X POST http://localhost:8003/v1/responses \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","input":"hi","max_output_tokens":50}'
```
