# 企业微信 (WeCom) 平台特性文档

WeComAdapter 是基于企业微信自建应用 API 构建的适配器，支持 Webhook 回调接收、消息加解密和多种消息类型收发。

---

## 文档信息

- 对应模块版本: 4.0.0
- 维护者: ErisPulse

## 基本信息

- 平台简介：企业微信（WeCom，原企业号/WeChat Work）是腾讯推出的企业级通讯与办公平台
- 适配器名称：WeComAdapter
- 平台注册名：`wecom`（别名 `wxwork`）
- 支持的协议/API版本：企业微信服务端 API
- 会话类型映射：应用消息 → `private`（用户私信），应用群聊 → `group`
- 接收模式：Webhook 被动接收（HTTP 回调）

## 多账户配置

每个账户对应一个企业微信自建应用，独立配置 `corpid` / `secret` / `agentid`，并拥有独立的 access_token 缓存。

```toml
[WeComAdapter.accounts.default]
corpid = "企业ID"
secret = "应用Secret"
agentid = 1000002
token = "回调Token"
encoding_aes_key = "43位加解密密钥"
callback_path = "/wecom/default"
enabled = true
```

### 配置字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `corpid` | string | 是 | 企业ID |
| `secret` | string | 是 | 应用 Secret |
| `agentid` | int | 否 | 应用 AgentID |
| `token` | string | 否 | 回调验证 Token |
| `encoding_aes_key` | string | 否 | 回调加解密密钥（43位） |
| `callback_path` | string | 否 | 回调路径，支持 `{account}` 占位符 |
| `enabled` | bool | 否 | 是否启用（默认 true） |

## 支持的消息发送类型

所有发送方法均通过链式语法实现，例如：
```python
from ErisPulse.Core import adapter
wecom = adapter.get("wecom")

await wecom.Send.To("user", "UserID").Text("Hello World!")
```

### 基本发送方法

| 方法 | 说明 | 参数 |
|------|------|------|
| `.Text(text)` | 发送纯文本消息 | `text: str` |
| `.Markdown(content)` | 发送 Markdown 消息（应用消息支持） | `content: str` |

### 媒体发送方法

媒体方法支持 `bytes`（自动上传获取 media_id）和 `str`（已上传的 media_id）两种输入：

| 方法 | 说明 |
|------|------|
| `.Image(file, filename)` | 发送图片 |
| `.Voice(file, filename)` | 发送语音 |
| `.Audio(file, filename)` | Voice 的别名 |
| `.Video(file, filename)` | 发送视频 |
| `.File(file, filename)` | 发送文件 |

### 富文本卡片方法

| 方法 | 说明 |
|------|------|
| `.News(articles)` | 发送图文消息（最多8条） |
| `.TextCard(title, description, url, btn_txt)` | 发送文本卡片 |
| `.TextCardMiniProgram(**kwargs)` | 发送小程序通知卡片 |
| `.TemplateCard(card_type, **kwargs)` | 发送模板卡片 |

### 原始消息发送

- `.Raw_ob12(message: List[Dict])`：发送 OneBot12 标准格式消息

### 链式修饰方法

| 方法 | 说明 |
|------|------|
| `.At(user_id)` | @指定用户（由框架 SendDSL 基类实现） |
| `.AtAll()` | @全体成员（由框架 SendDSL 基类实现） |
| `.Reply(message_id)` | 回复指定消息（由框架 SendDSL 基类实现） |

### 发送目标映射

| OB12 target_type | 企业微信目标字段 | API 接口 |
|---|---|---|
| `user` / `private` | `touser` | `message/send` |
| `group` | `chatid` | `appchat/send` |

### 发送示例

```python
# 基本文本发送
await wecom.Send.To("user", "UserID").Text("Hello World!")

# Markdown
await wecom.Send.To("user", "UserID").Markdown("**加粗** 和 [链接](https://example.com)")

# 图片（bytes 上传）
with open("image.png", "rb") as f:
    await wecom.Send.To("user", "UserID").Image(f.read(), filename="image.png")

# 图片（media_id）
await wecom.Send.To("user", "UserID").Image("media_id_xxx")

# 图文消息
await wecom.Send.To("user", "UserID").News([
    {"title": "标题1", "description": "描述1", "url": "https://example.com/1", "picurl": "https://example.com/1.jpg"},
])

# 文本卡片
await wecom.Send.To("user", "UserID").TextCard("标题", "描述", "https://example.com", btn_txt="查看详情")

# 发送到应用群聊
await wecom.Send.To("group", "ChatID").Text("群消息")

# 模板卡片
await wecom.Send.To("user", "UserID").TemplateCard(
    card_type="text_notice",
    main_title={"title": "欢迎使用"},
    emphasis_content={"title": "100", "desc": "处理量"},
)

# OneBot12 组合消息
ob12_message = [
    {"type": "text", "data": {"text": "你好："}},
    {"type": "image", "data": {"file": "media_id_xxx"}},
]
await wecom.Send.To("user", "UserID").Raw_ob12(ob12_message)

# 多账户指定账户发送
await wecom.Send.To("user", "UserID", account_id="app2").Text("通过 app2 发送")
```

## 特有事件类型

企业微信事件转换遵循 OneBot12 标准，同时通过 `wecom_` 前缀提供平台扩展。

### 消息事件 detail_type 映射

企业微信应用接收的消息统一映射为 `private`（私信）：

| 企业微信消息 | OneBot12 type / detail_type |
|---|---|
| `text` | `message` / `private` |
| `image` | `message` / `private` |
| `voice` | `message` / `private` |
| `video` / `shortvideo` | `message` / `private` |
| `location` | `message` / `private` |
| `link` | `message` / `private` |

### 特有事件类型（notice）

| detail_type | 说明 |
|---|---|
| `wecom_subscribe` | 用户关注 / 进入应用（subscribe / enter_agent） |
| `wecom_unsubscribe` | 用户取消关注 |
| `wecom_location_report` | 上报地理位置 |
| `wecom_menu_click` | 点击菜单跳转事件（click） |
| `wecom_menu_view` | 点击菜单链接跳转（view） |
| `wecom_scancode` | 扫码推事件 |
| `wecom_menu_photo` | 拍照/相册事件 |

### 标准消息段类型

转换后的消息段使用 OneBot12 标准格式：

| 消息段类型 | 说明 | data 字段 |
|---|---|---|
| `text` | 纯文本 | `text` |
| `image` | 图片 | `file`（PicUrl 或 MediaId），`url` |
| `audio` | 语音 | `file`（MediaId） |
| `video` | 视频 | `file`（MediaId），`thumbnail` |
| `location` | 位置 | `latitude`, `longitude`, `title` |
| `file` | 文件/链接 | `file`, `filename`, `url` |

### 平台扩展消息段

以 `wecom_` 前缀标识的扩展消息段（发送方向）：

| 消息段类型 | 说明 | data 字段 |
|---|---|---|
| `wecom_markdown` | Markdown 消息 | `content` |
| `wecom_news` | 图文消息 | `articles`（list） |
| `wecom_textcard` | 文本卡片 | `title`, `description`, `url`, `btntxt` |
| `wecom_miniprogram_notice` | 小程序通知 | 原生字段透传 |
| `wecom_template_card` | 模板卡片 | `card_type` + 原生字段 |

### 事件示例

#### 文本消息
```python
{
  "id": "1234567890123456",
  "time": 1348831860,
  "type": "message",
  "detail_type": "private",
  "platform": "wecom",
  "self": {"platform": "wecom", "user_id": "Corpid"},
  "user_id": "UserID",
  "user_nickname": "UserID",
  "message": [{"type": "text", "data": {"text": "消息内容"}}],
  "alt_message": "消息内容",
  "wecom_raw": {"MsgType": "text", "Content": "消息内容", "...": "..."},
  "wecom_raw_type": "text",
  "wecom_agentid": "1000002",
  "wecom_corpid": "Corpid",
  "wecom_msg_id": "1234567890123456"
}
```

#### 菜单点击事件
```python
{
  "type": "notice",
  "detail_type": "wecom_menu_click",
  "platform": "wecom",
  "user_id": "UserID",
  "wecom_event_key": "menu_key_1",
  "wecom_raw_type": "event"
}
```

## Event Mixin 扩展方法

适配器注册了以下平台专有方法，仅在 `platform == "wecom"` 时可用：

| 方法 | 返回类型 | 说明 |
|------|----------|------|
| `get_user_id()` | `str` | 获取发送者 UserID |
| `get_msg_type()` | `str` | 获取企业微信消息类型（text/image/...） |
| `get_content()` | `str` | 获取消息纯文本内容 |
| `get_agentid()` | `str` | 获取应用 AgentID |
| `get_corpid()` | `str` | 获取企业 Corpid |
| `get_msg_id()` | `str` | 获取消息 MsgId |
| `get_raw_xml()` | `str` | 获取解密后的原始 XML |
| `get_raw()` | `dict` | 获取解析后的原始数据字典 |
| `get_event_key()` | `str` | 获取菜单事件的 EventKey |
| `get_media_id()` | `str` | 获取媒体消息的 MediaId |

### 使用示例

```python
from ErisPulse.Core.Event import message, notice

@message.on_message()
async def handle_message(event):
    if event.get("platform") != "wecom":
        return

    msg_type = event.get_msg_type()
    user_id = event.get_user_id()
    content = event.get_content()
    agentid = event.get_agentid()

    if msg_type == "text":
        await event.reply(f"收到: {content}")

@notice.on_notice()
async def handle_notice(event):
    if event.get("platform") != "wecom":
        return

    if event.get("detail_type") == "wecom_menu_click":
        key = event.get_event_key()
        await event.reply(f"你点击了菜单: {key}")
```

## 扩展字段说明

- 所有特有字段均以 `wecom_` 前缀标识
- 保留原始数据在 `wecom_raw` 字段（解析后的字典）
- 保留解密后原始 XML 在 `wecom_raw_xml` 字段
- 保留原始事件类型在 `wecom_raw_type` 字段
- `wecom_corpid`：企业ID
- `wecom_agentid`：应用 AgentID
- `wecom_msg_id`：企业微信消息 ID

## 认证与加解密

### access_token 管理

- 每个账户独立缓存 access_token
- 有效期 7200 秒，提前 5 分钟自动刷新
- token 失效（errcode 40014/42001）时自动清除缓存并重试

### 消息加解密

- 算法：AES-256-CBC（PKCS7 填充）
- 密钥：`base64decode(EncodingAESKey + "=")`（32字节）
- IV：密钥前 16 字节
- 签名：`sha1("".join(sorted([token, timestamp, nonce, encrypt])))`
- 依赖库：`cryptography`

## 配置选项

企业微信适配器支持多账户配置，每个账户对应一个自建应用。详见上文「多账户配置」章节。
