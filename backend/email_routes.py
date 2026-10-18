from __future__ import annotations

import json
import re
import smtplib
import ssl
from base64 import b64decode
from datetime import date
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agent_tools import generate_email_draft, review_email_draft, supervisor_from_dict
from config import get_email_settings, get_model_settings
from storage import get_profile, get_supervisors, save_supervisors


router = APIRouter(prefix="/api/email", tags=["email"])
MAX_ATTACHMENT_FILE_SIZE = 8 * 1024 * 1024
MAX_ATTACHMENT_TOTAL_SIZE = 20 * 1024 * 1024
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


class EmailDraftRequest(BaseModel):
    supervisor_id: int
    tone: str = "正式版"


class EmailReviewRequest(BaseModel):
    supervisor_id: int
    subject: str
    body: str


class EmailAttachmentClearRequest(BaseModel):
    supervisor_id: int


class EmailSendRequest(BaseModel):
    supervisor_id: int
    subject: str
    body: str
    recipient: str = ""
    cc: str = ""
    attachment_note: str = ""
    attachment_files: list[str] = Field(default_factory=list)
    attachment_payloads: list[dict[str, Any]] = Field(default_factory=list)
    attachment_total_size: int = 0
    confirmed: bool = False


def _make_email_model() -> tuple[Any | None, str]:
    settings = get_model_settings()
    if not settings.configured:
        return None, "未检测到 .env 中可用的大模型配置"
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as error:
        return None, f"缺少 langchain_openai 依赖：{error}"
    return (
        ChatOpenAI(
            model=settings.model_id,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=settings.temperature,
        ),
        "",
    )


def _clean_header(value: str) -> str:
    return re.sub(r"[\r\n]+", " ", value or "").strip()


def _parse_email_list(value: str) -> list[str]:
    addresses: list[str] = []
    for part in re.split(r"[,;]", value or ""):
        _, address = parseaddr(part.strip())
        address = address.strip()
        if address and EMAIL_RE.match(address):
            addresses.append(address)
    return addresses


def _decode_attachments(payloads: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    attachments: list[dict[str, Any]] = []
    total_size = 0
    for item in payloads:
        name = _clean_header(str(item.get("name") or "attachment"))
        content_type = str(item.get("type") or "application/octet-stream")
        encoded = str(item.get("data") or "")
        try:
            content = b64decode(encoded, validate=True)
        except Exception:
            return [], f"附件 {name} 内容解析失败。"
        size = len(content)
        if size > MAX_ATTACHMENT_FILE_SIZE:
            return [], f"附件 {name} 超过单个文件大小限制。"
        total_size += size
        if total_size > MAX_ATTACHMENT_TOTAL_SIZE:
            return [], "附件总大小超过限制。"
        maintype, _, subtype = content_type.partition("/")
        attachments.append(
            {
                "name": name,
                "content": content,
                "maintype": maintype or "application",
                "subtype": subtype or "octet-stream",
            }
        )
    return attachments, ""


def _send_smtp_email(
    *,
    subject: str,
    body: str,
    recipient: str,
    cc: str = "",
    attachment_payloads: list[dict[str, Any]] | None = None,
) -> tuple[bool, str]:
    settings = get_email_settings()
    if not settings.configured:
        return (
            False,
            "邮件发送未启用。请在根目录 .env 中设置 EMAIL_SEND_ENABLED=true，并配置 SMTP_HOST、SMTP_PORT、SMTP_USERNAME、SMTP_PASSWORD、SMTP_FROM_EMAIL。",
        )
    if settings.use_ssl and settings.use_tls:
        return False, "SMTP 配置冲突：SSL 直连和 STARTTLS 不能同时启用。"
    if settings.smtp_host.lower() == "smtp.qq.com" and settings.smtp_port == 587 and settings.use_ssl:
        return False, "QQ 邮箱的 587 端口不能使用 SSL 直连；请改为 465 + SSL，或 587 + STARTTLS。"

    to_addresses = _parse_email_list(recipient)
    cc_addresses = _parse_email_list(cc)
    if not to_addresses:
        return False, "收件人邮箱格式不正确。"

    message = EmailMessage()
    message["From"] = formataddr((_clean_header(settings.from_name), settings.from_email))
    message["To"] = ", ".join(to_addresses)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    if settings.reply_to:
        message["Reply-To"] = settings.reply_to
    message["Subject"] = _clean_header(subject)
    message.set_content(body or "", subtype="plain", charset="utf-8")
    attachments, attachment_error = _decode_attachments(attachment_payloads or [])
    if attachment_error:
        return False, attachment_error
    for attachment in attachments:
        message.add_attachment(
            attachment["content"],
            maintype=attachment["maintype"],
            subtype=attachment["subtype"],
            filename=attachment["name"],
        )

    recipients = to_addresses + cc_addresses
    try:
        if settings.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.timeout_seconds,
                context=context,
            ) as server:
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message, from_addr=settings.from_email, to_addrs=recipients)
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.timeout_seconds,
            ) as server:
                server.ehlo()
                if settings.use_tls:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message, from_addr=settings.from_email, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP 登录失败，请检查邮箱账号和授权码/应用专用密码。"
    except smtplib.SMTPRecipientsRefused:
        return False, "SMTP 拒绝收件人地址，请检查导师邮箱或抄送邮箱。"
    except smtplib.SMTPException as error:
        return False, f"SMTP 发送失败：{error}"
    except OSError as error:
        return False, f"连接 SMTP 服务器失败：{error}"
    return True, "邮件已真实发送。"


@router.get("/config")
def email_config() -> dict[str, Any]:
    settings = get_model_settings()
    email_settings = get_email_settings()
    dependency_ready = True
    dependency_error = ""
    try:
        import langchain_openai  # noqa: F401
    except ImportError as error:
        dependency_ready = False
        dependency_error = str(error)
    return {
        "configured": settings.configured,
        "provider": settings.provider,
        "model_id": settings.model_id,
        "base_url": settings.base_url,
        "dependency_ready": dependency_ready,
        "dependency_error": dependency_error,
        "ready": settings.configured and dependency_ready,
        "smtp_configured": email_settings.configured,
        "smtp_host": email_settings.smtp_host,
        "smtp_port": email_settings.smtp_port,
        "smtp_use_ssl": email_settings.use_ssl,
        "smtp_use_tls": email_settings.use_tls,
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}


def _profile_payload(profile) -> dict[str, str]:
    return {
        "name": profile.name,
        "university": profile.university,
        "major": profile.major,
        "interests": profile.interests,
        "projects": profile.projects,
        "rank": profile.rank,
        "english": profile.english,
        "target_schools": profile.target_schools,
        "target_colleges": profile.target_colleges,
        "application_type": profile.application_type,
    }


def _supervisor_payload(supervisor) -> dict[str, Any]:
    return {
        "id": supervisor.id,
        "name": supervisor.name,
        "school": supervisor.school,
        "college": supervisor.college,
        "title": supervisor.title,
        "direction": supervisor.direction,
        "email": supervisor.email,
        "admission_type": supervisor.admission_type,
        "match_score": supervisor.match_score,
        "match_level": supervisor.match_level,
        "match_reason": supervisor.match_reason,
        "risk_note": supervisor.risk_note,
    }


def _generate_email_draft_with_ai(profile, supervisor, tone: str) -> dict[str, Any] | None:
    model, error_message = _make_email_model()
    if model is None:
        return {"ai_error": error_message}

    prompt = f"""
你是 GradMate 的研究生导师联系邮件助手。请基于学生画像和导师信息，为学生生成一封真实、礼貌、克制、针对性强的首次联系邮件。

要求：
1. 使用中文邮件格式。
2. 不要编造学生没有提供的经历、奖项、论文、导师招生计划。
3. 必须体现导师研究方向和学生兴趣/项目的连接。
4. 语气版本：{tone}。正式版更完整，简洁版更短。
5. 输出严格 JSON，不要 Markdown，不要解释。

JSON 格式：
{{
  "subject": "邮件主题",
  "body": "邮件正文，使用换行符分段"
}}

学生画像：
{json.dumps(_profile_payload(profile), ensure_ascii=False)}

导师信息：
{json.dumps(_supervisor_payload(supervisor), ensure_ascii=False)}
"""
    try:
        message = model.invoke(prompt)
    except Exception as error:
        return {"ai_error": str(error)}
    data = _extract_json_object(getattr(message, "content", str(message)))
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body") or "").strip()
    if not subject or not body:
        return {"ai_error": "模型未返回可解析的 subject/body JSON"}
    return {"subject": subject, "body": body, "ai_used": True}


def _review_email_with_ai(profile, supervisor, subject: str, body: str) -> dict[str, Any] | None:
    model, error_message = _make_email_model()
    if model is None:
        return {"ai_error": error_message}

    prompt = f"""
你是 GradMate 的导师联系邮件质量审查助手。请审查下面这封邮件是否适合发给研究生导师。

要求：
1. 根据学生画像、导师信息、邮件主题和正文审查。
2. 不要泛泛而谈，建议要具体、可执行。
3. 输出严格 JSON，不要 Markdown，不要解释。
4. checks 必须包含以下 5 项：称呼是否规范、是否针对导师方向、是否说明个人背景、是否说明附件、主题是否明确。

JSON 格式：
{{
  "score": 0到100的整数,
  "checks": [
    {{"label": "称呼是否规范", "passed": true或false}},
    {{"label": "是否针对导师方向", "passed": true或false}},
    {{"label": "是否说明个人背景", "passed": true或false}},
    {{"label": "是否说明附件", "passed": true或false}},
    {{"label": "主题是否明确", "passed": true或false}}
  ],
  "suggestions": ["建议1", "建议2"]
}}

学生画像：
{json.dumps(_profile_payload(profile), ensure_ascii=False)}

导师信息：
{json.dumps(_supervisor_payload(supervisor), ensure_ascii=False)}

邮件主题：
{subject}

邮件正文：
{body}
"""
    try:
        message = model.invoke(prompt)
    except Exception as error:
        return {"ai_error": str(error)}
    data = _extract_json_object(getattr(message, "content", str(message)))
    checks = data.get("checks")
    suggestions = data.get("suggestions")
    if not isinstance(checks, list) or not isinstance(suggestions, list):
        return {"ai_error": "模型未返回可解析的 checks/suggestions JSON"}
    try:
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    return {
        "score": max(0, min(100, score)),
        "checks": [
            {"label": str(item.get("label", "")), "passed": bool(item.get("passed"))}
            for item in checks
            if isinstance(item, dict) and item.get("label")
        ],
        "suggestions": [str(item) for item in suggestions if str(item).strip()],
        "ai_used": True,
    }


@router.post("/generate")
def generate_email(payload: EmailDraftRequest) -> dict[str, Any]:
    profile = get_profile()
    supervisors = get_supervisors()
    for item in supervisors:
        if int(item.get("id", 0)) == payload.supervisor_id:
            supervisor = supervisor_from_dict(item)
            draft = _generate_email_draft_with_ai(profile, supervisor, payload.tone)
            ai_error = draft.get("ai_error") if draft else ""
            if not draft or ai_error:
                draft = generate_email_draft(profile, supervisor, payload.tone)
                draft["ai_used"] = False
                if ai_error:
                    draft["ai_error"] = ai_error
            item["email_subject"] = draft["subject"]
            item["email_body"] = draft["body"]
            item["contact_status"] = "已生成草稿"
            item["contact_status_mode"] = "auto"
            item["email_generated_at"] = item.get("email_generated_at") or date.today().isoformat()
            save_supervisors(supervisors)
            review = _review_email_with_ai(profile, supervisor, draft["subject"], draft["body"])
            ai_error = review.get("ai_error") if review else ""
            if not review or ai_error:
                review = review_email_draft(profile, supervisor, draft["subject"], draft["body"])
                review["ai_used"] = False
                if ai_error:
                    review["ai_error"] = ai_error
            return {"supervisor": item, "draft": draft, "review": review}
    return {"error": "未找到导师"}


@router.post("/review")
def review_email(payload: EmailReviewRequest) -> dict[str, Any]:
    profile = get_profile()
    for item in get_supervisors():
        if int(item.get("id", 0)) == payload.supervisor_id:
            supervisor = supervisor_from_dict(item)
            review = _review_email_with_ai(profile, supervisor, payload.subject, payload.body)
            ai_error = review.get("ai_error") if review else ""
            if not review or ai_error:
                review = review_email_draft(profile, supervisor, payload.subject, payload.body)
                review["ai_used"] = False
                if ai_error:
                    review["ai_error"] = ai_error
            return {"review": review}
    return {"error": "未找到导师"}


@router.post("/attachments/clear")
def clear_email_attachments(payload: EmailAttachmentClearRequest) -> dict[str, Any]:
    supervisors = get_supervisors()
    for item in supervisors:
        if int(item.get("id", 0)) == payload.supervisor_id:
            item["email_attachment_note"] = ""
            item["email_attachment_files"] = []
            item["email_attachment_total_size"] = 0
            save_supervisors(supervisors)
            return {"cleared": True, "supervisor": item}
    return {"cleared": False, "message": "未找到导师。"}


@router.post("/send")
def confirm_email_send(payload: EmailSendRequest) -> dict[str, Any]:
    if not payload.confirmed:
        return {"sent": False, "message": "发送前必须由用户确认。"}
    if payload.attachment_total_size > MAX_ATTACHMENT_TOTAL_SIZE:
        return {"sent": False, "message": "附件总大小超过限制，不能确认发送。"}

    supervisors = get_supervisors()
    for item in supervisors:
        if int(item.get("id", 0)) == payload.supervisor_id:
            recipient = payload.recipient or item.get("email", "")
            if not recipient:
                return {"sent": False, "message": "导师邮箱缺失，不能确认发送。"}
            sent, message = _send_smtp_email(
                subject=payload.subject,
                body=payload.body,
                recipient=recipient,
                cc=payload.cc,
                attachment_payloads=payload.attachment_payloads,
            )
            if not sent:
                return {"sent": False, "message": message}
            item["email"] = item.get("email") or recipient
            item["email_subject"] = payload.subject
            item["email_body"] = payload.body
            item["email_cc"] = payload.cc
            item["email_attachment_note"] = payload.attachment_note
            item["email_attachment_files"] = payload.attachment_files
            item["email_attachment_total_size"] = payload.attachment_total_size
            item["contact_status"] = "已发送"
            item["contact_status_mode"] = "auto"
            item["email_sent_at"] = date.today().isoformat()
            item["contact_last_at"] = date.today().isoformat()
            save_supervisors(supervisors)
            return {
                "sent": True,
                "message": message,
                "supervisor": item,
                "smtp_sent": True,
            }
    return {"sent": False, "message": "未找到导师。"}
