import time
import uuid
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional


from ErisPulse.Core.Bases import BaseConverter


class WeComConverter(BaseConverter):
    """企业微信事件转换器

    将企业微信回调推送的明文 XML 转换为 OneBot12 标准事件。
    仅负责正向转换（接收方向），反向转换由 Send.Raw_ob12() 处理。
    """

    def __init__(self, platform: str = "wecom"):
        self.platform = platform
        # 机器人自身标识，默认空字符串；可由 Core 设置为 corpid
        self._bot_id: str = ""

    def set_bot_id(self, bot_id: str):
        self._bot_id = bot_id or ""

    def _parse_xml(self, xml_str: str) -> Dict[str, str]:
        """解析企业微信 XML 为扁平字典"""
        result: Dict[str, str] = {}
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            return result
        for child in root:
            result[child.tag] = (child.text or "").strip()
        return result

    def convert(self, raw_event) -> Optional[Dict]:
        """将企业微信明文 XML 转换为 OneBot12 标准事件

        :param raw_event: 解密后的明文 XML 字符串
        :return: OneBot12 标准事件字典，无法识别时返回 None
        """
        if not raw_event:
            return None

        if isinstance(raw_event, dict):
            data = raw_event
            raw_xml = raw_event.get("_raw_xml", "")
        else:
            raw_xml = raw_event if isinstance(raw_event, str) else str(raw_event)
            data = self._parse_xml(raw_xml)

        msg_type = data.get("MsgType", "")
        from_user = data.get("FromUserName", "")
        corpid = data.get("ToUserName", "") or self._bot_id
        create_time = self._to_int(data.get("CreateTime"), int(time.time()))
        msg_id = data.get("MsgId", "") or str(uuid.uuid4())
        agent_id = data.get("AgentID", "") or data.get("AgentId", "")

        bot_id = self._bot_id or corpid

        base: Dict = {
            "id": str(msg_id),
            "time": create_time,
            "platform": self.platform,
            "self": {
                "platform": self.platform,
                "user_id": str(bot_id),
            },
            "wecom_raw": dict(data),
            "wecom_raw_type": msg_type or "unknown",
            "wecom_raw_xml": raw_xml,
            "wecom_agentid": str(agent_id) if agent_id else "",
            "wecom_corpid": str(corpid) if corpid else "",
            "wecom_msg_id": str(msg_id) if msg_id else "",
        }

        if msg_type == "event":
            return self._convert_event(data, base, from_user)

        # 普通消息：企业微信应用消息一般为私信
        base["type"] = "message"
        base["detail_type"] = "private"
        base["user_id"] = str(from_user) if from_user else ""
        base["user_nickname"] = str(from_user) if from_user else ""

        message_segments, alt_message = self._convert_message_segments(data, msg_type)
        base["message"] = message_segments
        base["alt_message"] = alt_message

        return base

    def _convert_message_segments(self, data: Dict, msg_type: str):
        segments: List[Dict] = []
        alt_parts: List[str] = []

        if msg_type == "text":
            content = data.get("Content", "")
            segments.append({"type": "text", "data": {"text": content}})
            alt_parts.append(content)

        elif msg_type == "image":
            pic_url = data.get("PicUrl", "")
            media_id = data.get("MediaId", "")
            file_val = pic_url or media_id
            seg_data = {"file": file_val}
            if pic_url:
                seg_data["url"] = pic_url
            segments.append({"type": "image", "data": seg_data})
            alt_parts.append("[图片]")

        elif msg_type == "voice":
            media_id = data.get("MediaId", "")
            recognition = data.get("Recognition", "")
            seg_data = {"file": media_id}
            segments.append({"type": "audio", "data": seg_data})
            if recognition:
                segments.append({"type": "text", "data": {"text": recognition}})
                alt_parts.append(recognition)
            else:
                alt_parts.append("[语音]")

        elif msg_type == "video":
            media_id = data.get("MediaId", "")
            thumb = data.get("ThumbMediaId", "")
            segments.append(
                {"type": "video", "data": {"file": media_id, "thumbnail": thumb}}
            )
            alt_parts.append("[视频]")

        elif msg_type == "shortvideo":
            media_id = data.get("MediaId", "")
            segments.append({"type": "video", "data": {"file": media_id}})
            alt_parts.append("[小视频]")

        elif msg_type == "location":
            lat = self._to_float(data.get("Location_X"), 0.0)
            lon = self._to_float(data.get("Location_Y"), 0.0)
            label = data.get("Label", "")
            seg_data = {"latitude": lat, "longitude": lon}
            if label:
                seg_data["title"] = label
            segments.append({"type": "location", "data": seg_data})
            alt_parts.append(label or f"[位置] {lat},{lon}")

        elif msg_type == "link":
            title = data.get("Title", "")
            description = data.get("Description", "")
            url = data.get("Url", "")
            segments.append(
                {
                    "type": "file",
                    "data": {"file": url, "filename": title, "url": url},
                }
            )
            text = f"{title}\n{description}\n{url}".strip()
            segments.append({"type": "text", "data": {"text": text}})
            alt_parts.append(text or "[链接]")

        else:
            content = data.get("Content", "")
            if content:
                segments.append({"type": "text", "data": {"text": content}})
                alt_parts.append(content)
            else:
                segments.append({"type": "text", "data": {"text": f"[{msg_type}]"}})
                alt_parts.append(f"[{msg_type}]")

        return segments, "".join(alt_parts)

    def _convert_event(self, data: Dict, base: Dict, from_user: str) -> Dict:
        event = data.get("Event", "").lower()
        user_id = str(from_user) if from_user else ""

        base["type"] = "notice"
        base["user_id"] = user_id
        base["user_nickname"] = user_id

        if event in ("subscribe", "enter_agent"):
            base["detail_type"] = "wecom_subscribe"
        elif event == "unsubscribe":
            base["detail_type"] = "wecom_unsubscribe"
        elif event == "location":
            lat = self._to_float(data.get("Latitude"), 0.0)
            lon = self._to_float(data.get("Longitude"), 0.0)
            precision = self._to_float(data.get("Precision"), 0.0)
            base["detail_type"] = "wecom_location_report"
            base["message"] = [
                {
                    "type": "location",
                    "data": {"latitude": lat, "longitude": lon, "precision": precision},
                }
            ]
            base["alt_message"] = f"[位置上报] {lat},{lon}"
        elif event == "click":
            base["detail_type"] = "wecom_menu_click"
            base["wecom_event_key"] = data.get("EventKey", "")
        elif event == "view":
            base["detail_type"] = "wecom_menu_view"
            base["wecom_event_key"] = data.get("EventKey", "")
        elif event == "scancode_push":
            base["detail_type"] = "wecom_scancode"
            base["wecom_event_key"] = data.get("EventKey", "")
            base["wecom_scan_result"] = data.get("ScanResult", "")
        elif event == "pic_sysphoto" or event.startswith("pic_"):
            base["detail_type"] = "wecom_menu_photo"
        else:
            base["detail_type"] = f"wecom_{event}" if event else "wecom_event"
            base["wecom_event_key"] = data.get("EventKey", "")

        return base

    @staticmethod
    def _to_int(value, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
