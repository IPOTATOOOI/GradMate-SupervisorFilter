from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI

from agent_tools import (
    extract_supervisors_from_text,
    generate_email_draft,
    mmr_rerank,
    profile_from_dict,
    profile_summary,
    review_email_draft,
    score_supervisors_hybrid,
    supervisor_from_dict,
    supervisor_to_dict,
)
from browser_research import browse_school_supervisors, browser_progress
from config import get_model_settings, public_config
from ddl_service import get_baoyan_ddl
from export_tools import export_ddl_report, export_supervisors_report
from storage import (
    get_knowledge_items,
    get_profile,
    get_supervisors,
    load_system_prompt,
    save_assistant_history,
    save_profile,
    save_supervisors,
)


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def _task_terms(value: str) -> list[str]:
    terms = re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z0-9_+-]{2,}", value or "")
    ignored = {"根据", "我的", "个人", "背景", "帮我", "筛选", "导师", "最适合", "分别", "生成", "联系", "邮件", "草稿"}
    return [term for term in terms if term not in ignored]


def _supervisor_brief(item: dict[str, Any]) -> dict[str, Any]:
    """Keep raw page evidence out of tool responses and model prompts."""
    return {
        "id": int(item.get("id") or 0),
        "name": str(item.get("name") or ""),
        "school": str(item.get("school") or ""),
        "college": str(item.get("college") or ""),
        "title": str(item.get("title") or ""),
        "direction": str(item.get("direction") or ""),
        "email": str(item.get("email") or ""),
        "admission_type": str(item.get("admission_type") or ""),
        "match_score": int(item.get("match_score") or 0),
        "match_reason": str(item.get("match_reason") or "")[:240],
        "risk_note": str(item.get("risk_note") or "")[:160],
    }


@tool
def save_student_profile(profile_json: str) -> str:
    """
    保存学生画像。

    参数 `profile_json` 必须是 JSON 字符串，可包含姓名、本科院校、本科专业、研究兴趣、
    项目经历、成绩排名、英语水平、目标学校、目标学院和申请类型。适用于用户填写或更新
    个人申请背景时。
    """
    try:
        profile = profile_from_dict(json.loads(profile_json))
    except json.JSONDecodeError:
        return "保存失败：profile_json 不是合法 JSON。"
    save_profile(profile)
    return json.dumps({"profile": profile.__dict__, "summary": profile_summary(profile)}, ensure_ascii=False)


@tool
def get_student_profile() -> str:
    """Read the saved student profile and return a concise application summary."""
    profile = get_profile()
    return json.dumps({"profile": profile.__dict__, "summary": profile_summary(profile)}, ensure_ascii=False)


@tool
def search_supervisors(school: str = "", keywords: str = "", limit: int = 40) -> str:
    """Search the local supervisor database by school, college, research direction, and keywords."""
    school_key = _compact(school)
    terms = _task_terms(keywords)
    ranked: list[tuple[int, dict[str, Any]]] = []
    for item in get_supervisors():
        merged = " ".join(
            str(item.get(key) or "")
            for key in ("name", "school", "college", "title", "direction", "admission_type", "source")
        )
        compact = _compact(merged)
        if school_key and school_key not in _compact(item.get("school")):
            continue
        score = sum(1 for term in terms if _compact(term) in compact)
        ranked.append((score, item))
    ranked.sort(key=lambda pair: (pair[0], int(pair[1].get("match_score") or 0)), reverse=True)
    safe_limit = min(max(int(limit or 40), 1), 80)
    items = [_supervisor_brief(item) for _, item in ranked[:safe_limit]]
    return json.dumps({"count": len(items), "supervisors": items}, ensure_ascii=False)


@tool
def query_admission_kb(query: str, school: str = "", college: str = "", limit: int = 5) -> str:
    """Search uploaded admission documents and current admission DDL notices for cited evidence."""
    terms = _task_terms(" ".join([query, school, college]))
    records: list[tuple[int, dict[str, Any]]] = []
    for item in get_knowledge_items():
        text = str(item.get("text") or "")
        score = sum(1 for term in terms if _compact(term) in _compact(text))
        if score:
            records.append((score, {
                "source": item.get("source", "knowledge_base"),
                "kind": item.get("kind", "knowledge"),
                "snippet": text[:700],
            }))
    try:
        ddl = get_baoyan_ddl(query=school or college or query[:20], limit=20, refresh=False)
        for item in ddl.get("items", []):
            snippet = " ".join(str(item.get(key) or "") for key in ("name", "institute", "description", "deadline_date"))
            score = sum(1 for term in terms if _compact(term) in _compact(snippet))
            if score:
                records.append((score, {
                    "source": item.get("website") or ddl.get("source_label", "admission_ddl"),
                    "kind": "ddl",
                    "snippet": snippet[:700],
                }))
    except Exception:
        pass
    records.sort(key=lambda pair: pair[0], reverse=True)
    safe_limit = min(max(int(limit or 5), 1), 12)
    sources = [item for _, item in records[:safe_limit]]
    return json.dumps({"count": len(sources), "sources": sources}, ensure_ascii=False)


@tool
def extract_supervisors_tool(text: str, source: str = "用户上传资料") -> str:
    """
    从用户上传或粘贴的导师资料中抽取导师信息。

    适用于导师信息 Excel/CSV 文本、招生简章片段、学院官网复制文本、导师主页文本。
    返回导师姓名、学校、学院、职称、研究方向、邮箱、招生类型和信息来源；无法确认的字段
    保持为空，不能编造。
    """
    current = get_supervisors()
    start_id = max([int(item.get("id", 0)) for item in current] + [0]) + 1
    extracted = extract_supervisors_from_text(text=text, source=source, start_id=start_id)
    items = [supervisor_to_dict(item) for item in extracted]
    current.extend(items)
    save_supervisors(current)
    return json.dumps({"imported": len(items), "supervisors": current}, ensure_ascii=False)


@tool
def score_supervisor_match_tool() -> str:
    """
    根据当前保存的学生画像，对导师库进行匹配评分和排序。

    评分维度来自项目设计：研究方向 40%、招生类型 20%、目标院校/学院偏好 15%、
    项目经历相关性 15%、信息完整度/联系风险 10%。返回分数、等级、推荐理由和风险提示。
    """
    profile = get_profile()
    scored_supervisors = score_supervisors_hybrid(
        profile,
        [supervisor_from_dict(item) for item in get_supervisors()],
    )
    scored = [supervisor_to_dict(item) for item in scored_supervisors]
    save_supervisors(scored)
    return json.dumps({"supervisors": scored, "profile_summary": profile_summary(profile)}, ensure_ascii=False)


@tool
def generate_email_draft_tool(supervisor_id: int, tone: str = "正式版") -> str:
    """
    为指定导师生成联系邮件草稿。

    只生成单个导师的草稿，不会自动发送邮件。生成后会把草稿保存到导师记录中，
    供用户在邮件工作台预览、编辑和确认。
    """
    profile = get_profile()
    supervisors = get_supervisors()
    for item in supervisors:
        if int(item.get("id", 0)) == supervisor_id:
            supervisor = supervisor_from_dict(item)
            draft = generate_email_draft(profile, supervisor, tone)
            review = review_email_draft(profile, supervisor, draft["subject"], draft["body"])
            item["email_subject"] = draft["subject"]
            item["email_body"] = draft["body"]
            item["contact_status"] = "已生成草稿"
            save_supervisors(supervisors)
            return json.dumps({"draft": draft, "review": review, "supervisor": item}, ensure_ascii=False)
    return json.dumps({"error": "未找到导师"}, ensure_ascii=False)


@tool
def review_email_draft_tool(supervisor_id: int, subject: str, body: str) -> str:
    """
    审查指定导师的邮件草稿质量。

    检查称呼是否规范、是否针对导师方向、是否说明个人背景、是否说明附件、主题是否明确。
    """
    profile = get_profile()
    for item in get_supervisors():
        if int(item.get("id", 0)) == supervisor_id:
            review = review_email_draft(profile, supervisor_from_dict(item), subject, body)
            return json.dumps({"review": review}, ensure_ascii=False)
    return json.dumps({"error": "未找到导师"}, ensure_ascii=False)


@tool
def browse_school_supervisors_tool(
    school: str,
    major: str = "",
    college: str = "",
    keywords: str = "",
    max_pages: int = 12,
    task_id: str = "",
) -> str:
    """
    使用本地 ChromeDriver 打开浏览器，检索学校对应专业或学院官网，并继续查看导师、教师、师资队伍页面。
    适用于用户希望 Agent 自动补充导师资料来源时。必须提供 school，并提供 major 或 college。
    工具会把抽取到的导师信息写入本地导师库，并返回访问过的页面、候选链接和导入数量。
    """
    result = browse_school_supervisors(
        school=school,
        major=major,
        college=college,
        keywords=keywords,
        max_pages=max_pages,
        save=True,
        task_id=task_id,
    )
    return json.dumps({
        "school": result.get("school", school),
        "major": result.get("major", major),
        "college": result.get("college", college),
        "imported": result.get("imported", 0),
        "visited_page_count": len(result.get("visited_pages", [])),
        "candidate_link_count": len(result.get("candidate_links", [])),
        "trace": result.get("trace", [])[-8:],
    }, ensure_ascii=False)


@tool
def export_supervisors_report_tool(report_format: str = "docx") -> str:
    """
    Export the current supervisor database to a Word or Excel report.

    Use report_format="docx" for Word and report_format="xlsx" for Excel.
    The generated file is saved under WORD_REPORTS_DIR and the local path is returned.
    """
    fmt = (report_format or "docx").lower()
    if fmt not in {"docx", "xlsx"}:
        fmt = "docx"
    path = export_supervisors_report(get_supervisors(), report_format=fmt)
    return json.dumps({"path": str(path), "format": fmt}, ensure_ascii=False)


@tool
def export_ddl_report_tool(source: str = "camp2026", query: str = "", report_format: str = "docx") -> str:
    """
    Export admission DDL notices to a Word or Excel report.

    This mirrors the class demo pattern: the Agent chooses a tool, the Python tool
    writes a real document file, and the tool returns the generated file path.
    """
    fmt = (report_format or "docx").lower()
    if fmt not in {"docx", "xlsx"}:
        fmt = "docx"
    data = get_baoyan_ddl(source=source, query=query, limit=80, refresh=False)
    path = export_ddl_report(data.get("items", []), report_format=fmt)
    return json.dumps({"path": str(path), "format": fmt, "count": len(data.get("items", []))}, ensure_ascii=False)


TOOLS = [
    save_student_profile,
    get_student_profile,
    search_supervisors,
    query_admission_kb,
    extract_supervisors_tool,
    score_supervisor_match_tool,
    generate_email_draft_tool,
    review_email_draft_tool,
    browse_school_supervisors_tool,
    export_supervisors_report_tool,
    export_ddl_report_tool,
]


def create_gradmate_agent() -> tuple[Any | None, str]:
    """Create the LangChain agent only when a real model is configured."""
    system_prompt = load_system_prompt()
    settings = get_model_settings()

    if not settings.configured:
        return None, "unconfigured"

    model = ChatOpenAI(
        model=settings.model_id,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
    )
    return create_agent(model=model, tools=TOOLS, system_prompt=system_prompt), f"ChatOpenAI:{settings.model_id}"


AGENT, AGENT_MODE = create_gradmate_agent()


def agent_config() -> dict[str, Any]:
    return {
        "system_prompt": load_system_prompt(),
        "tools": [item.name for item in TOOLS],
        "agent_mode": AGENT_MODE,
        "agent_created": AGENT is not None,
        "config": public_config(),
    }


def _trace_event(event: str, name: str, message: str, detail: str = "") -> dict[str, str]:
    return {
        "event": event,
        "name": name,
        "message": message,
        "detail": detail,
        "time": datetime.now().strftime("%H:%M:%S"),
    }


def _json_result(value: Any) -> dict[str, Any]:
    try:
        return json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}


def _requested_count(task: str) -> int:
    """Extract an explicit recommendation count without silently returning extra people."""
    match = re.search(r"(?:前|最适合的?)\s*([一二三四五12345])\s*位", task)
    if not match:
        return 3
    values = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
    token = match.group(1)
    return values[token] if token in values else int(token)


def _extract_target_school(task: str) -> str:
    """Extract a university name without absorbing request verbs such as '帮我筛选'."""
    candidate = task
    for marker in ("帮我筛选", "筛选", "查询", "查找", "推荐", "寻找", "找出", "报考", "申请"):
        if marker in candidate:
            candidate = candidate.rsplit(marker, 1)[1]
            break
    match = re.search(r"([\u4e00-\u9fa5]{2,12}大学)", candidate)
    return match.group(1) if match else ""


def _model_json(prompt: str) -> dict[str, Any]:
    """Call the configured model and accept a JSON object, including fenced JSON."""
    settings = get_model_settings()
    if not settings.configured:
        return {}
    model = ChatOpenAI(
        model=settings.model_id,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=0,
        timeout=settings.timeout_seconds,
        max_retries=0,
    )
    response = model.invoke(prompt)
    content = getattr(response, "content", str(response))
    if not isinstance(content, str):
        content = str(content)
    direct = _json_result(content)
    if direct:
        return direct
    match = re.search(r"\{.*\}", content, re.S)
    return _json_result(match.group(0)) if match else {}


def run_application_assistant(message: str, on_event: Any = None) -> dict[str, Any]:
    """
    Execute a multi-tool application workflow for a natural-language request.

    The controller selects only the tools relevant to the goal, then emits the
    same event vocabulary used by LangChain astream_events so the UI can make
    the chain, tool starts, tool ends, and final model-style response visible.
    """
    task = (message or "").strip()
    if not task:
        return {"answer": "请输入希望 GradMate 协助完成的申请任务。", "events": [], "recommendations": []}

    task_id = uuid4().hex[:8]
    events: list[dict[str, str]] = []

    def emit(event: dict[str, str]) -> None:
        """Keep the HTTP response trace and the live SSE trace identical."""
        events.append(event)
        if on_event:
            on_event(event)

    emit(_trace_event("on_chain_start", "gradmate_application_agent", "正在分析申请任务并规划工具链……"))

    def call_tool(tool_item: Any, name: str, start_message: str, end_message: str, **kwargs: Any) -> dict[str, Any]:
        emit(_trace_event("on_tool_start", name, start_message))
        try:
            payload = _json_result(tool_item.invoke(kwargs))
            detail = ""
            if "count" in payload:
                detail = f"获得 {payload['count']} 条结果"
            elif "imported" in payload:
                detail = f"新增 {payload['imported']} 条导师资料"
            emit(_trace_event("on_tool_end", name, end_message, detail))
            return payload
        except Exception as error:
            emit(_trace_event("on_tool_end", name, "工具执行失败，已继续后续可用步骤。", str(error)[:180]))
            return {}

    profile_data = call_tool(get_student_profile, "get_student_profile", "正在读取学生画像……", "已读取学生画像。")
    settings = get_model_settings()
    intent: dict[str, Any] = {}
    if settings.configured:
        emit(_trace_event("on_chat_model_stream", "intent_parser", "大模型正在解析用户意图、目标院校与专业方向……"))
        try:
            intent = _model_json(f"""
你是 GradMate 的申请任务意图解析器。请从用户任务和学生画像中抽取结构化信息，不要臆造学校、专业或要求。
用户任务：{task}
学生画像：{profile_data.get('summary', '')}

只输出 JSON：{{"school":"吉林大学或空字符串","major":"计算机科学与技术或空字符串","college":"学院名称或空字符串","research_keywords":"人工智能 机器学习等关键词","recommendation_count":1,"needs_email":true,"reason":"简短解析说明"}}。
school 必须仅为学校全名（例如“吉林大学”），不能包含“帮我筛选”等任务动词；recommendation_count 必须是 1 到 5 的整数。
""")
            emit(_trace_event("on_chat_model_stream", "intent_parser", "大模型已完成用户意图解析。", str(intent.get("reason") or "")))
        except Exception as error:
            emit(_trace_event("on_chat_model_stream", "intent_parser", "大模型意图解析失败，已使用规则降级。", str(error)[:180]))
    else:
        emit(_trace_event("on_chat_model_stream", "intent_parser", "未配置大模型 API，正在使用规则解析用户意图。"))

    model_school = str(intent.get("school") or "").strip()
    school = model_school if re.fullmatch(r"[\u4e00-\u9fa5]{2,20}大学", model_school) else _extract_target_school(task)
    model_count = intent.get("recommendation_count")
    requested_count = int(model_count) if str(model_count).isdigit() and 1 <= int(model_count) <= 5 else _requested_count(task)
    intent_major = str(intent.get("major") or "").strip()
    intent_keywords = str(intent.get("research_keywords") or "").strip()
    search_data = call_tool(
        search_supervisors,
        "search_supervisors",
        f"正在检索{school or '目标院校'}导师信息……",
        "导师检索完成。",
        school=school,
        keywords=intent_keywords or task,
        limit=20,
    )
    admission_data = call_tool(
        query_admission_kb,
        "query_admission_kb",
        "正在检索招生资料和相关通知……",
        "招生资料检索完成。",
        query=task,
        school=school,
        limit=5,
    )

    initial_candidates = search_data.get("supervisors", [])
    planner: dict[str, Any] = {}
    if settings.configured:
        emit(_trace_event("on_chat_model_stream", "application_planner", "大模型正在根据任务、画像和初步检索结果规划下一步工具……"))
        try:
            planner = _model_json(f"""
你是 GradMate 的申请任务规划 Agent。你只能依据给出的数据作判断，不能虚构导师。
用户任务：{task}
学生画像：{profile_data.get('summary', '')}
目标学校：{school or '未明确'}
用户期望推荐人数：{requested_count}
初步导师结果（JSON）：{json.dumps(initial_candidates[:20], ensure_ascii=False)}
招生资料（JSON）：{json.dumps(admission_data.get('sources', [])[:5], ensure_ascii=False)}

判断现有结果是否足够完成任务。若学校明确，非该学校导师绝不可视为候选；若相关导师数量不足、研究方向不相符或关键信息缺失，应要求调用浏览器官网检索工具。
只输出 JSON：{{"should_browse":true,"browse_major":"计算机科学与技术","browse_keywords":"人工智能 导师","reason":"简短理由"}}。
""")
            emit(_trace_event("on_chat_model_stream", "application_planner", "大模型已完成工具规划。", str(planner.get("reason") or "")))
        except Exception as error:
            emit(_trace_event("on_chat_model_stream", "application_planner", "大模型规划调用失败，已按保守规则继续。", str(error)[:180]))
    else:
        emit(_trace_event("on_chat_model_stream", "application_planner", "未配置大模型 API，当前使用保守规则编排；不会声称进行了模型判断。"))

    school_candidates = [
        item for item in initial_candidates
        if not school or _compact(item.get("school")) == _compact(school)
    ]
    needs_browse = bool(planner.get("should_browse")) if settings.configured else False
    needs_browse = needs_browse or (bool(school) and len(school_candidates) < requested_count)
    if needs_browse and school:
        browser_progress_scope = browser_progress(lambda detail: emit(_trace_event(
            "on_tool_progress",
            "browse_school_supervisors",
            "正在浏览目标学校导师页面……",
            detail[:360],
        )))
        browser_progress_scope.__enter__()
        major = str(planner.get("browse_major") or "").strip() or intent_major or "计算机"
        keywords = str(planner.get("browse_keywords") or "").strip() or intent_keywords or "研究生导师"
        call_tool(
            browse_school_supervisors_tool,
            "browse_school_supervisors",
            f"现有候选不足或不符合意图，正在检索{school}官网导师资料……",
            f"{school}官网导师检索完成。",
            school=school,
            major=major,
            keywords=keywords,
            max_pages=12,
            task_id=task_id,
        )
        browser_progress_scope.__exit__(None, None, None)
        search_data = call_tool(
            search_supervisors,
            "search_supervisors",
            f"正在重新筛选{school}相关导师……",
            "已更新导师候选集。",
            school=school,
            keywords=intent_keywords or task,
            limit=20,
        )

    call_tool(
        score_supervisor_match_tool,
        "match_supervisors",
        "正在结合学生画像计算导师匹配结果……",
        "导师匹配计算完成。",
    )

    candidate_ids = {int(item.get("id") or 0) for item in search_data.get("supervisors", [])}
    candidates = [
        item for item in get_supervisors()
        if int(item.get("id") or 0) in candidate_ids
        and (not school or _compact(item.get("school")) == _compact(school))
    ]
    candidates.sort(key=lambda item: int(item.get("match_score") or 0), reverse=True)
    selected_ids: list[int] = []
    if settings.configured and candidates:
        prompt_candidates = [_supervisor_brief(item) for item in candidates[:20]]
        emit(_trace_event("on_chat_model_stream", "supervisor_relevance_judge", "大模型正在核验导师方向与用户意图的符合度……"))
        try:
            judgement = _model_json(f"""
你是 GradMate 的导师匹配审查员。只能从候选 JSON 中选择，不能创建或补充任何姓名；目标学校明确时，只能选择该学校导师。
用户意图：{task}
学生画像：{profile_data.get('summary', '')}
目标学校：{school or '未明确'}
需要人数：{requested_count}
候选导师（已由规则匹配打分，JSON）：{json.dumps(prompt_candidates, ensure_ascii=False)}
输出 JSON：{{"selected_ids":[1],"reason":"简短说明"}}。selected_ids 最多 {requested_count} 个。
""")
            allowed_ids = {int(item.get("id") or 0) for item in candidates}
            selected_ids = [int(item) for item in judgement.get("selected_ids", []) if str(item).isdigit() and int(item) in allowed_ids][:requested_count]
            emit(_trace_event("on_chat_model_stream", "supervisor_relevance_judge", "大模型已完成候选符合度核验。", str(judgement.get("reason") or "")))
        except Exception as error:
            emit(_trace_event("on_chat_model_stream", "supervisor_relevance_judge", "大模型核验失败，已按匹配评分排序。", str(error)[:180]))
    if selected_ids:
        order = {item_id: index for index, item_id in enumerate(selected_ids)}
        candidates.sort(key=lambda item: order.get(int(item.get("id") or 0), len(order)))
    diversity_pool = candidates[:requested_count] if selected_ids else candidates
    diverse = mmr_rerank(
        [supervisor_from_dict(item) for item in diversity_pool],
        limit=requested_count,
    )
    candidates = [supervisor_to_dict(item) for item in diverse]
    recommendations: list[dict[str, Any]] = []
    needs_email = bool(re.search(r"邮件|联系|套磁", task)) or (
        settings.configured and bool(intent.get("needs_email"))
    )
    for supervisor in candidates:
        recommendation = {
            "id": supervisor.get("id"),
            "name": supervisor.get("name") or "待确认导师",
            "school": supervisor.get("school") or "",
            "college": supervisor.get("college") or "",
            "direction": supervisor.get("direction") or "",
            "email": supervisor.get("email") or "",
            "score": int(supervisor.get("match_score") or 0),
            "reason": supervisor.get("match_reason") or "基于当前画像计算得到的匹配结果。",
            "risk": supervisor.get("risk_note") or "",
        }
        if needs_email and recommendation["id"]:
            draft_data = call_tool(
                generate_email_draft_tool,
                "generate_email_draft",
                f"正在为 {recommendation['name']} 生成联系邮件草稿……",
                f"已保存 {recommendation['name']} 的邮件草稿。",
                supervisor_id=int(recommendation["id"]),
                tone="正式版",
            )
            draft = draft_data.get("draft", {})
            recommendation["draft"] = draft
            review_data = call_tool(
                review_email_draft_tool,
                "review_email_draft",
                f"正在审查 {recommendation['name']} 的邮件质量……",
                "邮件质量审查完成。",
                supervisor_id=int(recommendation["id"]),
                subject=str(draft.get("subject") or ""),
                body=str(draft.get("body") or ""),
            )
            recommendation["review"] = review_data.get("review", {})
        recommendations.append(recommendation)

    if recommendations:
        names = "、".join(str(item["name"]) for item in recommendations)
        answer = f"已完成任务链，优先推荐 {names}。结果已按匹配分数排序"
        if needs_email:
            answer += "，并已为每位推荐导师生成、审查并保存邮件草稿。"
        else:
            answer += "。"
    else:
        answer = f"当前导师库中没有找到与{school or '该任务'}相符的可推荐导师。可先在“导师资料”页面补充或检索院系官网信息。"

    emit(_trace_event("on_chat_model_stream", "gradmate_application_agent", "正在整理工具调用结果并生成建议……"))
    emit(_trace_event("on_chain_end", "gradmate_application_agent", "任务链执行完成。"))
    result = {
        "answer": answer,
        "recommendations": recommendations,
        "admission_sources": admission_data.get("sources", []),
        "profile_summary": profile_data.get("summary", ""),
        "events": events,
        "agent_mode": AGENT_MODE,
    }
    # A history record is saved only after the entire tool chain has completed,
    # so reopening it always restores a coherent result and trace.
    try:
        save_assistant_history({"message": task, **result})
    except Exception:
        # History must never make the main application task fail.
        pass
    return result


def invoke_agent(message: str) -> dict[str, Any]:
    """Run the configured LangChain agent directly."""
    if AGENT is None:
        raise RuntimeError("未配置可用的大模型，无法调用 Agent。")
    result = AGENT.invoke({"messages": [{"role": "user", "content": message}]})
    messages = result.get("messages", [])
    last = messages[-1].content if messages else ""
    return {"reply": last, "agent_mode": AGENT_MODE}
