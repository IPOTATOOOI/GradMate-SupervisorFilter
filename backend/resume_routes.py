from __future__ import annotations

import json
import re
from io import BytesIO
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from config import get_model_settings
from storage import get_profile, get_resume_draft, save_resume_draft


router = APIRouter(prefix="/api/resume", tags=["resume"])


def _extract_resume_upload_text(filename: str, content: bytes) -> str:
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    if suffix == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as error:
            raise HTTPException(status_code=500, detail="后端缺少 pypdf，无法解析 PDF。请重新安装 backend/requirements.txt。") from error
        try:
            reader = PdfReader(BytesIO(content))
            text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
            if not text:
                raise HTTPException(status_code=400, detail="PDF 中没有提取到可用文字，可能是扫描图片版 PDF。请先 OCR 或粘贴文本。")
            return text
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=400, detail=f"PDF 解析失败：{error}") from error

    for encoding in ["utf-8-sig", "utf-8", "gb18030"]:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="暂不支持该文件编码或文件类型。")


class ResumeGenerateRequest(BaseModel):
    target: str = ""
    resume_text: str = ""
    highlights: str = ""
    style: str = "保研导师联系"


class ResumeReviewRequest(BaseModel):
    target: str = ""
    resume_text: str


class ResumeDraftRequest(BaseModel):
    target: str = ""
    highlights: str = ""
    source_text: str = ""
    generated: str = ""
    sections: list[str] = []
    suggestions: list[str] = []
    review: dict[str, Any] | None = None
    upload_name: str = ""
    photo: str = ""
    photo_name: str = ""
    style: str = "保研导师联系"


@router.get("/draft")
def read_resume_draft() -> dict[str, Any]:
    return {"draft": get_resume_draft()}


@router.post("/draft")
def write_resume_draft(payload: ResumeDraftRequest) -> dict[str, Any]:
    # The browser limits images to 2MB before upload. Keep an explicit backend
    # guard as well because this state is stored in SQLite.
    if len(payload.photo.encode("utf-8")) > 3 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="证件照数据过大，请使用 2MB 以内的图片。")
    payload_data = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
    return {"draft": save_resume_draft(payload_data)}


@router.post("/upload-file")
async def upload_resume_file(file: UploadFile = File(...)) -> dict[str, Any]:
    content = await file.read()
    if len(content) > 12 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 12MB。")
    text = _extract_resume_upload_text(file.filename or "", content)
    if not text.strip():
        raise HTTPException(status_code=400, detail="文件中没有提取到可用文本。")
    return {"filename": file.filename, "text": text, "text_length": len(text)}


def _make_resume_model() -> tuple[Any | None, str]:
    settings = get_model_settings()
    if not settings.configured:
        return None, "未检测到可用的大模型配置。"
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


def _profile_payload() -> dict[str, str]:
    profile = get_profile()
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


@router.post("/generate")
def generate_resume(payload: ResumeGenerateRequest) -> dict[str, Any]:
    model, error_message = _make_resume_model()
    if model is None:
        raise HTTPException(status_code=503, detail=error_message)

    prompt = f"""
你是 GradMate 的 AI 简历顾问，面向保研、夏令营、导师联系和研究生申请场景。
请基于学生画像、已有简历/补充材料和目标方向，生成一份真实、克制、结构清晰、可直接复制的中文申请简历。

要求：
1. 不编造论文、竞赛、奖项、实习和量化结果；缺失内容用“待补充”或给出建议。
2. 重点突出研究兴趣、项目经历、方法工具、与目标导师方向的契合。
3. 使用 Markdown 结构，标题清晰，适合后续导出或粘贴到文档。
4. 返回严格 JSON，不要 Markdown 包裹，不要解释。

JSON 格式：
{{
  "resume": "完整 Markdown 简历正文",
  "sections": ["栏目1", "栏目2"],
  "suggestions": ["后续补充建议1", "建议2"]
}}

学生画像：
{json.dumps(_profile_payload(), ensure_ascii=False)}

目标方向/JD/导师要求：
{payload.target}

已有简历或粘贴材料：
{payload.resume_text}

希望突出的亮点：
{payload.highlights}

风格：
{payload.style}
"""
    try:
        message = model.invoke(prompt)
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"模型调用失败：{error}") from error
    data = _extract_json_object(getattr(message, "content", str(message)))
    resume = str(data.get("resume") or "").strip()
    if not resume:
        raise HTTPException(status_code=502, detail="模型未返回可解析的 resume 字段。")
    return {
        "resume": resume,
        "sections": [str(item) for item in data.get("sections", []) if str(item).strip()],
        "suggestions": [str(item) for item in data.get("suggestions", []) if str(item).strip()],
        "ai_used": True,
    }


@router.post("/review")
def review_resume(payload: ResumeReviewRequest) -> dict[str, Any]:
    model, error_message = _make_resume_model()
    if model is None:
        resume_text = payload.resume_text.strip()
        target_terms = {term.lower() for term in re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z0-9+#.-]{2,}", payload.target)}
        resume_lower = resume_text.lower()
        checks = [
            {"label": "内容非空", "passed": bool(resume_text)},
            {"label": "包含分节标题", "passed": bool(re.search(r"(?m)^#{1,3}\s+\S+", resume_text))},
            {"label": "正文达到 200 字", "passed": len(resume_text) >= 200},
            {
                "label": "包含目标方向关键词",
                "passed": bool(target_terms) and any(term in resume_lower for term in target_terms),
            },
        ]
        score = round(sum(int(item["passed"]) for item in checks) / len(checks) * 100)
        suggestions = [error_message]
        suggestions.extend(f"请改进：{item['label']}。" for item in checks if not item["passed"])
        return {
            "score": score,
            "suggestions": suggestions,
            "checks": checks,
            "ai_used": False,
        }

    prompt = f"""
你是研究生申请简历审查助手。请审查简历是否适合投递导师/夏令营/预推免。
只返回严格 JSON。

JSON 格式：
{{
  "score": 0到100的整数,
  "checks": [
    {{"label": "结构完整", "passed": true}},
    {{"label": "目标契合", "passed": true}},
    {{"label": "经历可验证", "passed": true}},
    {{"label": "科研表达", "passed": true}}
  ],
  "suggestions": ["具体修改建议"]
}}

目标方向：
{payload.target}

简历正文：
{payload.resume_text}
"""
    try:
        message = model.invoke(prompt)
    except Exception as error:
        return {"score": 0, "checks": [], "suggestions": [str(error)], "ai_used": False}
    data = _extract_json_object(getattr(message, "content", str(message)))
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    suggestions = data.get("suggestions") if isinstance(data.get("suggestions"), list) else []
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
