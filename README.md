[English](README.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md) | [日本語](README.ja.md) | [Русский](README.ru.md)

<div align="center">

<img src="https://raw.githubusercontent.com/ErisPulse/ErisPulse/main/.github/assets/ErisPulseLogo.png" width="180" alt="ErisPulse-WeComAdapter" />

# ErisPulse-WeComAdapter

**ErisPulse adapter for WeCom — callback receive, app messages & contacts API**

<p>
  <a href="https://pypi.org/project/ErisPulse-WeComAdapter/"><img src="https://img.shields.io/pypi/v/ErisPulse-WeComAdapter?style=for-the-badge&logo=pypi&logoColor=white" alt="PyPI"></a>
  <a href="https://pypi.org/project/ErisPulse-WeComAdapter/"><img src="https://img.shields.io/badge/Python-3.10+-FFD43B?style=for-the-badge&logo=python&logoColor=blue" alt="Python"></a>
  <a href="https://github.com/ErisPulse/ErisPulse/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue?style=for-the-badge" alt="License"></a>
  <img src="https://raw.githubusercontent.com/ErisPulse/.github/main/assets/badges/adapter.svg" alt="ErisPulse">
</p>

</div>

---

## 特性

- **多账户支持**：每个账户对应一个企业微信自建应用，独立 access_token 缓存
- **Webhook 被动接收**：自动注册回调路由，处理 URL 验证与消息推送
- **消息加解密**：基于 `cryptography` 库实现企业微信 AES-256-CBC 加解密与签名验证
- **丰富消息类型**：文本、Markdown、图片、语音、视频、文件、图文、文本卡片、模板卡片
- **OneBot12 标准**：事件遵循 OneBot12 规范，平台扩展字段以 `wecom_` 前缀标识

## 安装

```bash
epsdk install WeComAdapter
```

## 配置

在 `config/config.toml` 中添加：

```toml
[WeComAdapter.accounts.default]
corpid = "你的企业ID"
secret = "你的应用Secret"
agentid = 1000002
token = "回调验证Token"
encoding_aes_key = "回调加解密密钥（43位）"
callback_path = "/wecom/default"
enabled = true

# 多账户示例
[WeComAdapter.accounts.app2]
corpid = "你的企业ID"
secret = "另一个应用的Secret"
agentid = 1000003
token = "回调验证Token"
encoding_aes_key = "回调加解密密钥（43位）"
callback_path = "/wecom/app2"
enabled = true
```

### 配置字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `corpid` | string | 是 | 企业ID（Corpid） |
| `secret` | string | 是 | 应用 Secret |
| `agentid` | int | 否 | 应用 AgentID（发送消息时使用） |
| `token` | string | 否 | 回调验证 Token（企业微信后台设置） |
| `encoding_aes_key` | string | 否 | 回调加解密密钥 EncodingAESKey（43位） |
| `callback_path` | string | 否 | 回调接收路径，支持 `{account}` 占位符（默认 `/wecom/{account}`） |
| `enabled` | bool | 否 | 是否启用（默认 true） |
| `bot_id` | string | 否 | 自动取 corpid，无需手动填写 |

### 回调地址配置

在企业微信管理后台「自建应用 → 接收消息 → 设置API接收」中，将 URL 填为：

```
http(s)://<你的服务器地址>:<端口>/wecom/<账户名>
```

并填入对应的 Token 和 EncodingAESKey。适配器会自动处理 URL 验证（GET）和消息推送（POST）。

## 快速开始

```python
from ErisPulse import sdk
from ErisPulse.Core.Event import command, message

@command("hello")
async def hello_handler(event):
    await event.reply("Hello from WeCom!")

async def main():
    await sdk.run(keep_running=True)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

## 消息发送

所有发送方法通过链式 DSL 调用：

```python
wecom = sdk.adapter.get("wecom")

# 文本消息（私信用户）
await wecom.Send.To("user", "UserID1").Text("Hello World!")

# Markdown 消息
await wecom.Send.To("user", "UserID1").Markdown("**加粗** 消息")

# 发送到群聊（应用群聊）
await wecom.Send.To("group", "ChatID").Text("群消息")

# 图片（支持 media_id 或 bytes 上传）
await wecom.Send.To("user", "UserID1").Image("media_id")
await wecom.Send.To("user", "UserID1").Image(image_bytes, filename="pic.png")

# 图文消息
await wecom.Send.To("user", "UserID1").News([
    {"title": "标题", "description": "描述", "url": "https://example.com", "picurl": "https://example.com/img.jpg"},
])

# 文本卡片
await wecom.Send.To("user", "UserID1").TextCard(
    title="卡片标题", description="卡片描述",
    url="https://example.com", btn_txt="点击查看"
)

# 文件 / 语音 / 视频
await wecom.Send.To("user", "UserID1").File(file_bytes, filename="doc.pdf")
await wecom.Send.To("user", "UserID1").Voice(voice_bytes)
await wecom.Send.To("user", "UserID1").Video(video_bytes)

# 模板卡片
await wecom.Send.To("user", "UserID1").TemplateCard(
    card_type="text_notice",
    main_title={"title": "欢迎使用"},
    emphasis_content={"title": "100", "desc": "处理量"},
    sub_title_text="这是一条模板卡片",
)

# OneBot12 组合消息
ob12_message = [
    {"type": "text", "data": {"text": "你好！"}},
    {"type": "reply", "data": {"message_id": "12345"}},
]
await wecom.Send.To("user", "UserID1").Raw_ob12(ob12_message)

# 多账户指定账户发送
await wecom.Send.To("user", "UserID1", account_id="app2").Text("通过 app2 发送")
```

### 发送目标映射

| OB12 target_type | 企业微信目标 | 接口 |
|---|---|---|
| `user` / `private` | `touser`（用户消息） | `message/send` |
| `group` | `chatid`（应用群聊） | `appchat/send` |

## 依赖

- `cryptography`：用于 AES-256-CBC 消息加解密

## 许可证

MIT License
