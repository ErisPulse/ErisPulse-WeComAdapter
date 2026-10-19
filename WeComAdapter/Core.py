import asyncio
import base64
import hashlib
import io
import json
import socket
import struct
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from ErisPulse.Core import client, router
from ErisPulse.Core.Bases.adapter import BaseAdapter
from ErisPulse.Core.Event import register_event_mixin, unregister_platform_event_methods
from ErisPulse.Core.Bases import BotAccountConfig
from ErisPulse.Core.Bases.config_schema import dict_to_dataclass

from .Converter import WeComConverter

__version__ = "0.1.0"

# 软依赖的框架最低版本（运行时检测，仅提示不强制）
MIN_FRAMEWORK_VERSION = (2, 7, 1)


def _forward_node_text(node: Dict) -> str:
    """提取合并转发节点 content 中全部 text 段文本（段间直接连接）"""
    data = node.get("data") or {}
    return "".join(
        str(seg.get("data", {}).get("text") or "")
        for seg in (data.get("content") or [])
        if isinstance(seg, dict) and seg.get("type") == "text"
    )


def _forward_nodes_plain(nodes, separator: str = "\n") -> str:
    """合并转发节点降级纯文本：每条「昵称: 正文」（WeCom 无合并转发/富文本折叠能力）"""
    lines = []
    for node in nodes if isinstance(nodes, list) else [nodes]:
        if not isinstance(node, dict):
            continue
        data = node.get("data") or {}
        nickname = str(data.get("nickname") or "").strip()
        text = _forward_node_text(node).strip()
        if nickname and text:
            lines.append(f"{nickname}: {text}")
        elif text:
            lines.append(text)
    return separator.join(lines)

# ───────────────────────── 配置 ─────────────────────────


@dataclass
class WeComAccountConfig(BotAccountConfig):
    """企业微信应用账户配置（一个账户 = 一个企业微信自建应用）"""

    corpid: str = field(
        default="",
        metadata={
            "description": "企业ID（Corpid）",
            "required": True,
            "secret": True,
            "ui": {"widget": "text", "group": "basic", "order": 1},
        },
    )
    secret: str = field(
        default="",
        metadata={
            "description": "应用 Secret",
            "required": True,
            "secret": True,
            "ui": {"widget": "password", "group": "basic", "order": 2},
        },
    )
    agentid: int = field(
        default=0,
        metadata={
            "description": "应用 AgentID",
            "required": False,
            "ui": {"widget": "number", "group": "basic", "order": 3},
        },
    )
    token: str = field(
        default="",
        metadata={
            "description": "回调验证 Token（企业微信后台设置的 Token）",
            "required": False,
            "secret": True,
            "ui": {"widget": "password", "group": "callback", "order": 4},
        },
    )
    encoding_aes_key: str = field(
        default="",
        metadata={
            "description": "回调加解密密钥 EncodingAESKey（43位）",
            "required": False,
            "secret": True,
            "ui": {"widget": "password", "group": "callback", "order": 5},
        },
    )
    callback_path: str = field(
        default="/wecom/{account}",
        metadata={
            "description": "回调接收路径，支持 {account} 占位符",
            "required": False,
            "ui": {"widget": "text", "group": "callback", "order": 6},
        },
    )


# ───────────────────────── 平台扩展方法 ─────────────────────────


class WeComEventMixin:
    """企业微信事件平台扩展方法（仅 platform == 'wecom' 时可用）"""

    def get_user_id(self) -> str:
        return self.get("user_id", "")

    def get_msg_type(self) -> str:
        return self.get("wecom_raw_type", "")

    def get_content(self) -> str:
        return self.get("alt_message", "")

    def get_agentid(self) -> str:
        return self.get("wecom_agentid", "")

    def get_corpid(self) -> str:
        return self.get("wecom_corpid", "")

    def get_msg_id(self) -> str:
        return self.get("wecom_msg_id", "")

    def get_raw_xml(self) -> str:
        return self.get("wecom_raw_xml", "")

    def get_raw(self) -> dict:
        return self.get("wecom_raw", {}) or {}

    def get_event_key(self) -> str:
        return self.get("wecom_event_key", "")

    def get_media_id(self) -> str:
        for seg in self.get("message", []):
            seg_type = seg.get("type", "")
            if seg_type in ("image", "audio", "video", "file"):
                return seg.get("data", {}).get("file", "") or seg.get("data", {}).get(
                    "file_id", ""
                )
        return ""


register_event_mixin("wecom", WeComEventMixin)
# 兼容 wxwork 别名
try:
    register_event_mixin("wxwork", WeComEventMixin)
except Exception:
    pass


# ───────────────────────── 适配器主类 ─────────────────────────


class WeComAdapter(BaseAdapter):
    """企业微信（WeCom）适配器

    采用 Webhook 被动接收模式：企业微信通过 HTTP POST 把加密消息推送到
    配置的回调路径，适配器验证签名、解密 XML 后转换为 OneBot12 标准事件。
    """

    AccountConfigClass = WeComAccountConfig

    API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"

    # ─────────── Send 类 ───────────

    class Send(BaseAdapter.Send):
        def Text(self, text: str):
            return self.Raw_ob12([{"type": "text", "data": {"text": text}}])

        def Markdown(self, content: str):
            return self.Raw_ob12(
                [{"type": "wecom_markdown", "data": {"content": content}}]
            )

        def Image(self, file: Union[str, bytes], filename: str = "image.png"):
            if isinstance(file, bytes):
                return self.Raw_ob12(
                    [{"type": "image", "data": {"_raw_bytes": file, "file": filename}}]
                )
            return self.Raw_ob12([{"type": "image", "data": {"file": file}}])

        def Voice(self, file: Union[str, bytes], filename: str = "voice.amr"):
            if isinstance(file, bytes):
                return self.Raw_ob12(
                    [{"type": "audio", "data": {"_raw_bytes": file, "file": filename}}]
                )
            return self.Raw_ob12([{"type": "audio", "data": {"file": file}}])

        def Audio(self, file: Union[str, bytes], filename: str = "voice.amr"):
            return self.Voice(file, filename)

        def Video(self, file: Union[str, bytes], filename: str = "video.mp4"):
            if isinstance(file, bytes):
                return self.Raw_ob12(
                    [{"type": "video", "data": {"_raw_bytes": file, "file": filename}}]
                )
            return self.Raw_ob12([{"type": "video", "data": {"file": file}}])

        def File(self, file: Union[str, bytes], filename: str = "file.bin"):
            if isinstance(file, bytes):
                return self.Raw_ob12(
                    [{"type": "file", "data": {"_raw_bytes": file, "file": filename}}]
                )
            return self.Raw_ob12([{"type": "file", "data": {"file": file}}])

        def News(self, articles: List[Dict]):
            """发送图文消息

            :param articles: [{"title","description","url","picurl"}, ...]（最多8条）
            """
            return self.Raw_ob12(
                [{"type": "wecom_news", "data": {"articles": articles}}]
            )

        def TextCard(
            self,
            title: str,
            description: str,
            url: str,
            btn_txt: str = "详情",
            pic_media_id: str = "",
        ):
            data = {
                "title": title,
                "description": description,
                "url": url,
                "btntxt": btn_txt,
            }
            if pic_media_id:
                data["media_id"] = pic_media_id
            return self.Raw_ob12([{"type": "wecom_textcard", "data": data}])

        def TextCardMiniProgram(self, **kwargs):
            """小程序通知卡片，kwargs 直接透传为 miniprogram_notice 体"""
            return self.Raw_ob12([{"type": "wecom_miniprogram_notice", "data": kwargs}])

        def TemplateCard(self, card_type: str = "text_notice", **kwargs):
            """模板卡片

            :param card_type: text_notice / image_text_notice / news_notice / button_interaction
                              / vote_interaction / multiple_interaction
            """
            payload = {"card_type": card_type}
            payload.update(kwargs)
            return self.Raw_ob12([{"type": "wecom_template_card", "data": payload}])

        def Raw_ob12(self, message: Union[Dict, List[Dict]], **kwargs):
            if isinstance(message, dict):
                message = [message]

            # node 段降级为纯文本原文输出（内容不丢失）
            message = [
                {"type": "text", "data": {"text": _forward_nodes_plain(seg)}}
                if isinstance(seg, dict) and seg.get("type") == "node"
                else seg
                for seg in message
            ]

            segments = self._apply_modifiers(message)

            async def _send():
                ctx = self.send_context
                account_id = kwargs.get("account_id") or ctx.get("account_id")
                target_type = kwargs.get("target_type") or ctx.get("target_type")
                target_id = kwargs.get("target_id") or ctx.get("target_id")
                return await self._adapter._send_wecom(
                    segments,
                    account_id,
                    target_type,
                    target_id,
                )

            return asyncio.create_task(_send())

    # ─────────── 初始化与配置 ───────────

    def __init__(self, sdk_ref=None):
        super().__init__(sdk_ref)
        self._running = False
        # 每账户 access_token 缓存：{account_name: {"access_token": str, "expires_at": float}}
        self._token_cache: Dict[str, Dict[str, Any]] = {}
        # 每账户 Converter
        self._converters: Dict[str, WeComConverter] = {}

        self._check_framework_version()
        self._get_logger().info(f"WeComAdapter v{__version__} 已加载")

    @staticmethod
    def _parse_version(version_str: str) -> tuple:
        """解析版本号为可比较的三元组（忽略 dev/预发布后缀，如 2.8.0-dev.3 → (2, 8, 0)）"""
        parts = []
        for piece in str(version_str).split("."):
            digits = "".join(ch for ch in piece if ch.isdigit())
            parts.append(int(digits) if digits else 0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def _check_framework_version(self):
        """软依赖检测：框架版本过低时打警告（不阻断加载）"""
        try:
            from importlib.metadata import version as _pkg_version

            raw = _pkg_version("ErisPulse")
        except Exception:
            return
        try:
            if self._parse_version(raw) < MIN_FRAMEWORK_VERSION:
                self._get_logger().warning(
                    f"当前 ErisPulse 版本 {raw} 过低：WeComAdapter v{__version__} 需要 >= "
                    f"{'.'.join(map(str, MIN_FRAMEWORK_VERSION))}，"
                    "部分功能可能不可用，建议升级框架"
                )
        except Exception:
            pass

    # ==================== Api DSL（最小集） ====================

    class Api(BaseAdapter.Api):
        """企业微信标准 API 动作实现（最小集）"""

        async def get_self_info(self) -> dict:
            account_name, account = self._adapter._resolve_account(self._account_id)
            return self._adapter.make_response(
                data={
                    "user_id": str(account.corpid),
                    "user_name": f"wecom:{account_name}",
                    "agentid": str(getattr(account, "agentid", "")),
                }
            )

        async def get_status(self) -> dict:
            ad = self._adapter
            bots = []
            for name, account in ad.accounts.items():
                bots.append({
                    "self": {"platform": ad.platform, "user_id": str(account.corpid), "account_id": name},
                    "online": ad._running and name in ad._converters,
                })
            return ad.make_response(data={"good": any(b["online"] for b in bots), "bots": bots})

        async def get_version(self) -> dict:
            from . import __version__

            return self._adapter.make_response(
                data={"impl": "ErisPulse-WeComAdapter", "version": __version__, "onebot_version": "12"}
            )

        async def get_supported_actions(self) -> dict:
            actions = {"get_self_info", "get_status", "get_version", "get_supported_actions"}
            return self._adapter.make_response(data=sorted(actions))

    def _get_config_key(self) -> str:
        return "WeComAdapter"

    def _load_accounts(self) -> dict:
        from ErisPulse.Core.config import config as config_mgr
        from ErisPulse.runtime.config_schema import dict_to_dataclass

        key = "WeComAdapter.accounts"
        data = config_mgr.getConfig(key)

        if not data:
            self.logger.info("未找到配置文件，创建默认企业微信账户配置")
            default_config = {
                "default": {
                    "corpid": "",
                    "secret": "",
                    "agentid": 0,
                    "token": "",
                    "encoding_aes_key": "",
                    "callback_path": "/wecom/default",
                    "enabled": True,
                }
            }
            try:
                config_mgr.setConfig(key, default_config)
            except Exception as e:
                self.logger.error(f"保存默认账户配置失败: {str(e)}")
            data = default_config

        accounts = {}
        for name, account_data in data.items():
            if not isinstance(account_data, dict):
                continue

            if not account_data.get("corpid") or not account_data.get("secret"):
                self.logger.error(f"账户 {name} 缺少 corpid 或 secret 配置，已跳过")
                continue

            instance = dict_to_dataclass(WeComAccountConfig, account_data)
            instance.name = name

            # 解析回调路径中的占位符
            if not instance.callback_path:
                instance.callback_path = f"/wecom/{name}"
            else:
                instance.callback_path = instance.callback_path.replace(
                    "{account}", name
                )

            accounts[name] = instance

        self.logger.info(f"企业微信适配器初始化完成，共加载 {len(accounts)} 个账户")
        return accounts

    # ─────────── access_token 管理 ───────────

    async def _get_access_token(self, account_name) -> Tuple[bool, str]:
        """获取/刷新指定账户的 access_token（缓存，提前5分钟刷新）

        :return: (success, access_token_or_error_message)
        """
        cached = self._token_cache.get(account_name)
        now = time.time()
        # 提前 5 分钟刷新
        if cached and cached.get("expires_at", 0) - now > 300:
            return True, cached["access_token"]

        account = self.accounts.get(account_name)
        if not account:
            return False, f"账户 {account_name} 不存在"

        url = (
            f"{self.API_BASE}/gettoken"
            f"?corpid={account.corpid}&corpsecret={account.secret}"
        )
        try:
            resp = await client.get(url)
            raw = await resp.json()
        except Exception as e:
            return False, f"获取 access_token 网络失败: {str(e)}"

        if not isinstance(raw, dict) or raw.get("errcode", -1) != 0:
            msg = (
                raw.get("errmsg", "unknown")
                if isinstance(raw, dict)
                else "invalid response"
            )
            return False, f"获取 access_token 失败: {msg}"

        token = raw.get("access_token", "")
        expires_in = raw.get("expires_in", 7200)
        self._token_cache[account_name] = {
            "access_token": token,
            "expires_at": now + expires_in,
        }
        self.logger.debug(
            f"账户 {account_name} access_token 已刷新，有效期 {expires_in}s"
        )
        return True, token

    # ─────────── call_api ───────────

    async def call_api(
        self, endpoint: str, _account_id: Optional[str] = None, **params
    ):
        """调用企业微信 API（自动注入 access_token）

        :param endpoint: 接口路径，如 "message/send" 或完整 URL
        :param _account_id: 账户名
        """
        account_name, account = self._resolve_account(_account_id)
        echo = params.pop("echo", None)

        ok, token = await self._get_access_token(account_name)
        if not ok:
            err = self.make_error(retcode=33001, message=token, raw=None)
            if echo:
                err["echo"] = echo
            return err

        # 处理 multipart 上传（media/upload）
        upload_data = params.pop("_upload", None)  # (file_bytes, filename, type)

        if endpoint.startswith("http"):
            url = endpoint
        else:
            sep = "&" if "?" in endpoint else "?"
            url = f"{self.API_BASE}/{endpoint}{sep}access_token={token}"

        try:
            if upload_data:
                file_bytes, filename, media_type = upload_data
                import aiohttp

                form = aiohttp.FormData()
                form.add_field(
                    "media",
                    io.BytesIO(file_bytes),
                    filename=filename,
                    content_type="application/octet-stream",
                )
                resp = await client.post(url, data=form, timeout=300)
            else:
                resp = await client.post(url, json=params, timeout=60)

            raw_response = await resp.json()
            self.logger.debug(f"WeCom API [{endpoint}] 响应: {raw_response}")
        except Exception as e:
            self.logger.error(f"调用企业微信 API 失败 [{endpoint}]: {str(e)}")
            err = self.make_error(
                retcode=33001, message=f"API调用失败: {str(e)}", raw=None
            )
            if echo:
                err["echo"] = echo
            return err

        if not isinstance(raw_response, dict):
            err = self.make_error(
                retcode=34000,
                message=f"API 返回了意外格式: {type(raw_response)}",
                raw=raw_response,
            )
            if echo:
                err["echo"] = echo
            return err

        errcode = raw_response.get("errcode", -1)
        is_ok = errcode == 0

        # access_token 失效时清除缓存以便下次重试
        if errcode in (40014, 42001):
            self._token_cache.pop(account_name, None)

        message_id = str(raw_response.get("msgid", ""))

        resp_obj = self.make_response(
            status="ok" if is_ok else "failed",
            retcode=0 if is_ok else errcode,
            data=raw_response,
            message_id=message_id,
            message="" if is_ok else raw_response.get("errmsg", "Unknown error"),
            raw=raw_response,
        )
        resp_obj["wecom_raw"] = raw_response
        if echo:
            resp_obj["echo"] = echo
        return resp_obj

    # ─────────── 发送逻辑 ───────────

    async def _upload_media(
        self, account_name: str, file_bytes: bytes, filename: str, media_type: str
    ) -> Optional[str]:
        """上传临时素材，返回 media_id"""
        result = await self.call_api(
            f"media/upload?type={media_type}",
            _account_id=account_name,
            _upload=(file_bytes, filename, media_type),
        )
        if result.get("status") == "ok":
            media_id = result.get("data", {}).get("media_id", "")
            if media_id:
                return media_id
        self.logger.error(f"上传素材失败: {result.get('message')}")
        return None

    async def _send_wecom(
        self, segments: List[Dict], account_id: str, target_type: str, target_id: str
    ):
        """根据 OneBot12 消息段构建企业微信消息并发送"""
        account_name, account = self._resolve_account(account_id)
        converter = self._converters.get(account_name)
        if converter is None:
            converter = WeComConverter("wecom")
            converter.set_bot_id(account.corpid)
            self._converters[account_name] = converter

        # 目标映射：private/user → touser；group → chatid (appchat/send)
        is_group = target_type in ("group", "channel")
        target_param = {}
        if is_group:
            target_param["chatid"] = target_id
            endpoint = "appchat/send"
        else:
            target_param["touser"] = target_id
            endpoint = "message/send"

        # 从消息段中提取发送内容
        payload = await self._build_wecom_payload(
            account_name, segments, target_param, account.agentid
        )
        if payload is None:
            return self.make_error(
                retcode=34000,
                message="无法从消息段构建企业微信消息",
                raw=None,
            )

        return await self.call_api(endpoint, _account_id=account_name, **payload)

    async def _build_wecom_payload(
        self, account_name: str, segments: List[Dict], base: Dict, agentid: int
    ) -> Optional[Dict]:
        """将 OneBot12 消息段列表转换为企业微信发送体"""
        if not segments:
            return None

        # 找出主消息段（第一个非 mention/reply）
        main_seg = None
        text_parts: List[str] = []
        for seg in segments:
            seg_type = seg.get("type", "")
            data = seg.get("data", {})
            if seg_type == "text":
                text_parts.append(data.get("text", ""))
            elif main_seg is None and seg_type not in (
                "mention",
                "mention_all",
                "reply",
            ):
                main_seg = seg

        # 所有内容都是纯文本
        if main_seg is None:
            full_text = "".join(text_parts)
            if not full_text:
                full_text = " "
            return {
                **base,
                "msgtype": "text",
                "agentid": agentid,
                "text": {"content": full_text},
                "safe": 0,
            }

        seg_type = main_seg.get("type", "")
        data = main_seg.get("data", {})

        # 如果主段是文本，但仍可能有其他文本段，合并
        if seg_type == "text":
            full_text = "".join(text_parts) or data.get("text", " ")
            return {
                **base,
                "msgtype": "text",
                "agentid": agentid,
                "text": {"content": full_text},
                "safe": 0,
            }

        if seg_type == "image":
            raw_bytes = data.get("_raw_bytes")
            if raw_bytes:
                media_id = await self._upload_media(
                    account_name, raw_bytes, data.get("file", "image.png"), "image"
                )
                if not media_id:
                    return None
            else:
                media_id = data.get("file", "") or data.get("file_id", "")
            return {
                **base,
                "msgtype": "image",
                "agentid": agentid,
                "image": {"media_id": media_id},
            }

        if seg_type == "audio":
            raw_bytes = data.get("_raw_bytes")
            if raw_bytes:
                media_id = await self._upload_media(
                    account_name, raw_bytes, data.get("file", "voice.amr"), "voice"
                )
                if not media_id:
                    return None
            else:
                media_id = data.get("file", "") or data.get("file_id", "")
            return {
                **base,
                "msgtype": "voice",
                "agentid": agentid,
                "voice": {"media_id": media_id},
            }

        if seg_type == "video":
            raw_bytes = data.get("_raw_bytes")
            if raw_bytes:
                media_id = await self._upload_media(
                    account_name, raw_bytes, data.get("file", "video.mp4"), "video"
                )
                if not media_id:
                    return None
            else:
                media_id = data.get("file", "") or data.get("file_id", "")
            return {
                **base,
                "msgtype": "video",
                "agentid": agentid,
                "video": {"media_id": media_id},
            }

        if seg_type == "file":
            raw_bytes = data.get("_raw_bytes")
            if raw_bytes:
                media_id = await self._upload_media(
                    account_name, raw_bytes, data.get("file", "file.bin"), "file"
                )
                if not media_id:
                    return None
            else:
                media_id = data.get("file", "") or data.get("file_id", "")
            return {
                **base,
                "msgtype": "file",
                "agentid": agentid,
                "file": {"media_id": media_id},
            }

        if seg_type == "wecom_markdown":
            return {
                **base,
                "msgtype": "markdown",
                "agentid": agentid,
                "markdown": {"content": data.get("content", "")},
            }

        if seg_type == "wecom_news":
            return {
                **base,
                "msgtype": "news",
                "agentid": agentid,
                "news": {"articles": data.get("articles", [])},
            }

        if seg_type == "wecom_textcard":
            return {
                **base,
                "msgtype": "textcard",
                "agentid": agentid,
                "textcard": {
                    "title": data.get("title", ""),
                    "description": data.get("description", ""),
                    "url": data.get("url", ""),
                    "btntxt": data.get("btntxt", "详情"),
                },
            }

        if seg_type == "wecom_miniprogram_notice":
            return {
                **base,
                "msgtype": "miniprogram_notice",
                "agentid": agentid,
                "miniprogram_notice": data,
            }

        if seg_type == "wecom_template_card":
            return {
                **base,
                "msgtype": "template_card",
                "agentid": agentid,
                "template_card": data,
            }

        # 兜底：作为文本发送
        full_text = "".join(text_parts) or seg_type
        return {
            **base,
            "msgtype": "text",
            "agentid": agentid,
            "text": {"content": full_text},
            "safe": 0,
        }

    # ─────────── 加解密与签名 ───────────

    @staticmethod
    def _get_aes_key(encoding_aes_key: str) -> bytes:
        """从 EncodingAESKey 推导 AES 密钥（base64 解码 43位+("=")）"""
        return base64.b64decode(encoding_aes_key + "=")

    @classmethod
    def _verify_signature(
        cls, token: str, timestamp: str, nonce: str, encrypt: str, msg_signature: str
    ) -> bool:
        """验证企业微信消息签名"""
        items = sorted([token, timestamp, nonce, encrypt])
        sha1 = hashlib.sha1("".join(items).encode("utf-8")).hexdigest()
        return sha1 == msg_signature

    @classmethod
    def _decrypt(cls, encoding_aes_key: str, encrypted: str) -> Tuple[str, str]:
        """AES-256-CBC 解密

        :return: (明文消息XML, 企业Corpid)
        """
        key = cls._get_aes_key(encoding_aes_key)
        iv = key[:16]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()

        encrypted_bytes = base64.b64decode(encrypted)
        plain_padded = decryptor.update(encrypted_bytes) + decryptor.finalize()

        # 去除 PKCS7 填充
        pad_len = plain_padded[-1]
        if isinstance(pad_len, int) and 1 <= pad_len <= 32:
            plain = plain_padded[:-pad_len]
        else:
            plain = plain_padded

        # 16字节随机串 + 4字节网络序消息长度 + 明文XML + Corpid
        msg_len = socket.ntohl(struct.unpack("I", plain[16:20])[0])
        msg_xml = plain[20 : 20 + msg_len].decode("utf-8")
        corpid = plain[20 + msg_len :].decode("utf-8")
        return msg_xml, corpid

    @classmethod
    def _encrypt(cls, encoding_aes_key: str, corpid: str, reply_msg: str) -> str:
        """AES-256-CBC 加密回复消息，返回 base64"""
        key = cls._get_aes_key(encoding_aes_key)
        iv = key[:16]

        msg_bytes = reply_msg.encode("utf-8")
        corpid_bytes = corpid.encode("utf-8")
        random_bytes = b"\x00" * 16
        msg_len = struct.pack("I", socket.htonl(len(msg_bytes)))

        plain = random_bytes + msg_len + msg_bytes + corpid_bytes

        # PKCS7 填充到 32 字节倍数
        block_size = 32
        pad_len = block_size - (len(plain) % block_size)
        if pad_len == 0:
            pad_len = block_size
        plain += bytes([pad_len]) * pad_len

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(plain) + encryptor.finalize()
        return base64.b64encode(encrypted).decode("utf-8")

    @classmethod
    def _generate_signature(
        cls, token: str, timestamp: str, nonce: str, encrypt: str
    ) -> str:
        items = sorted([token, timestamp, nonce, encrypt])
        return hashlib.sha1("".join(items).encode("utf-8")).hexdigest()

    @classmethod
    def _build_encrypted_reply(
        cls,
        token: str,
        encoding_aes_key: str,
        corpid: str,
        reply_msg: str,
        timestamp: str,
        nonce: str,
    ) -> str:
        """构建加密回复 XML（用于被动回复消息）"""
        encrypt = cls._encrypt(encoding_aes_key, corpid, reply_msg)
        signature = cls._generate_signature(token, timestamp, nonce, encrypt)
        return (
            f"<xml>"
            f"<Encrypt><![CDATA[{encrypt}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
            f"<TimeStamp>{timestamp}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            f"</xml>"
        )

    # ─────────── Webhook 处理 ───────────

    def _get_query(self, request, key: str, default: str = "") -> str:
        """兼容地从 request 对象获取 query 参数"""
        for attr in ("query_params", "query"):
            q = getattr(request, attr, None)
            if q is not None:
                try:
                    val = q.get(key, default)
                    return val if val is not None else default
                except Exception:
                    try:
                        return q[key]
                    except Exception:
                        pass
        return default

    def _get_method(self, request) -> str:
        method = getattr(request, "method", "")
        if not method:
            method = getattr(request, "method", "POST") or "POST"
        return str(method).upper()

    async def _process_webhook(self, request, account_name: str):
        """处理企业微信回调请求（URL 验证 + 消息推送）"""
        account = self.accounts.get(account_name)
        if not account:
            self.logger.error(f"回调账户 {account_name} 不存在")
            return {"error": "unknown account"}

        timestamp = self._get_query(request, "timestamp", "")
        nonce = self._get_query(request, "nonce", "")
        msg_signature = self._get_query(request, "msg_signature", "")
        method = self._get_method(request)

        # 无加密配置时无法处理
        if not account.encoding_aes_key or not account.token:
            self.logger.error(
                f"账户 {account_name} 未配置 encoding_aes_key 或 token，无法处理回调"
            )
            return {"error": "missing crypto config"}

        # URL 验证（GET 请求）
        if method == "GET":
            echostr = self._get_query(request, "echostr", "")
            if not echostr:
                return {"error": "missing echostr"}

            if not self._verify_signature(
                account.token, timestamp, nonce, echostr, msg_signature
            ):
                self.logger.warning(f"账户 {account_name} URL验证签名失败")
                return {"error": "signature verification failed"}

            try:
                plain_echostr, _ = self._decrypt(account.encoding_aes_key, echostr)
                # 返回解密后的 echostr 明文
                return _PlainTextResponse(plain_echostr)
            except Exception as e:
                self.logger.error(f"账户 {account_name} 解密 echostr 失败: {str(e)}")
                return {"error": "decrypt failed"}

        # 消息/事件推送（POST 请求）
        try:
            body = await request.text()
        except Exception:
            try:
                body = (await request.read()).decode("utf-8", errors="ignore")
            except Exception as e:
                self.logger.error(f"账户 {account_name} 读取请求体失败: {str(e)}")
                return {"error": "read body failed"}

        # 解析外层 XML，提取 Encrypt 字段
        try:
            root = ET.fromstring(body)
            encrypt_elem = root.find("Encrypt")
            encrypt = (
                (encrypt_elem.text or "").strip() if encrypt_elem is not None else ""
            )
        except ET.ParseError:
            self.logger.error(f"账户 {account_name} 回调 XML 解析失败")
            return "success"

        if not encrypt:
            self.logger.warning(f"账户 {account_name} 回调缺少 Encrypt 字段")
            return "success"

        # 验证签名
        if not self._verify_signature(
            account.token, timestamp, nonce, encrypt, msg_signature
        ):
            self.logger.warning(f"账户 {account_name} 消息签名验证失败")
            return "success"

        # 解密
        try:
            plain_xml, recv_corpid = self._decrypt(account.encoding_aes_key, encrypt)
        except Exception as e:
            self.logger.error(f"账户 {account_name} 消息解密失败: {str(e)}")
            return "success"

        # 转换并分发
        converter = self._converters.get(account_name)
        if converter is None:
            converter = WeComConverter("wecom")
            self._converters[account_name] = converter

        bot_id = account.corpid or recv_corpid
        converter.set_bot_id(bot_id)

        try:
            onebot_event = converter.convert(plain_xml)
            self.logger.debug(
                f"账户 {account_name} OneBot12事件: "
                f"{json.dumps(onebot_event, ensure_ascii=False) if onebot_event else 'None'}"
            )
            if onebot_event:
                from ErisPulse.Core import adapter as adapter_mgr

                await adapter_mgr.emit(onebot_event)
        except Exception as e:
            self.logger.error(f"账户 {account_name} 事件处理失败: {str(e)}")

        # 企业微信要求在 5 秒内返回，默认返回 success
        return "success"

    # ─────────── 生命周期 ───────────

    async def start(self):
        self._running = True

        if not self.enabled_accounts:
            self.logger.warning("没有已启用的企业微信账户，适配器将以空闲状态启动")
            return

        for account_name, account in self.enabled_accounts.items():
            # 初始化 Converter
            converter = WeComConverter("wecom")
            converter.set_bot_id(account.corpid)
            self._converters[account_name] = converter

            path = account.callback_path or f"/wecom/{account_name}"

            # 创建闭包，捕获 account_name
            def make_webhook_handler(name):
                async def webhook_handler(request):
                    return await self._process_webhook(request, name)

                return webhook_handler

            try:
                router.register_http_route(
                    f"wecom_{account_name}",
                    path,
                    make_webhook_handler(account_name),
                    methods=["GET", "POST"],
                )
            except Exception as e:
                self.logger.error(
                    f"注册账户 {account_name} 回调路由 {path} 失败: {str(e)}"
                )
                continue

            self.logger.info(
                f"已注册账户 {account_name} (corpid: {account.corpid}, "
                f"agentid: {account.agentid}) 的回调路由: {path}"
            )

            # 发送 connect meta
            await self.emit_meta("connect", account.corpid, user_name=account_name)

        self.logger.info(
            f"企业微信适配器启动完成，共 {len(self.enabled_accounts)} 个账户"
        )

    async def shutdown(self):
        self._running = False

        for account_name, account in self.enabled_accounts.items():
            path = account.callback_path or f"/wecom/{account_name}"
            try:
                router.unregister_http_route(f"wecom_{account_name}", path)
            except Exception:
                pass

            try:
                await self.emit_meta("disconnect", account.corpid)
            except Exception:
                pass

        self._token_cache.clear()

        try:
            unregister_platform_event_methods("wecom")
        except Exception:
            pass

        self.logger.info("企业微信适配器已关闭")


class _PlainTextResponse:
    """包装明文响应，供 router 原样返回（URL 验证场景需要返回纯文本 echostr）"""

    def __init__(self, text: str):
        self.text = text
