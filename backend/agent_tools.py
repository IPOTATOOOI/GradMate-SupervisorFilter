from __future__ import annotations

import csv
import io
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TITLE_RE = re.compile(r"(教授|副教授|讲师|研究员|副研究员|博导|硕导)")
NAME_RE = re.compile(r"([\u4e00-\u9fa5]{2,4})(?:\s*)(教授|副教授|老师|研究员|副研究员|讲师)")

FIELD_ALIASES = {
    "name": ["name", "姓名", "导师", "导师姓名", "老师"],
    "school": ["school", "学校", "院校"],
    "college": ["college", "学院", "院系", "单位"],
    "title": ["title", "职称", "职位"],
    "direction": ["direction", "研究方向", "方向", "领域"],
    "email": ["email", "邮箱", "邮件"],
    "admission_type": ["admission_type", "招生类型", "类型"],
    "source": ["source", "来源", "信息来源"],
}


@dataclass
class StudentProfile:
    name: str = ""
    university: str = ""
    major: str = ""
    interests: str = ""
    projects: str = ""
    rank: str = ""
    english: str = ""
    target_schools: str = ""
    target_colleges: str = ""
    application_type: str = "保研"


@dataclass
class Supervisor:
    id: int
    name: str = "待确认导师"
    school: str = ""
    college: str = ""
    title: str = ""
    direction: str = ""
    email: str = ""
    admission_type: str = ""
    source: str = "用户上传资料"
    raw_text: str = ""
    match_score: int = 0
    match_level: str = "未评分"
    match_reason: str = ""
    risk_note: str = ""
    contact_status: str = "未联系"
    email_subject: str = ""
    email_body: str = ""
    email_review: str = ""
    match_breakdown: dict[str, float] = field(default_factory=dict)
    ranking_method: str = "hybrid_tfidf_rules"


def profile_summary(profile: StudentProfile) -> str:
    """Generate a concise, deterministic profile summary for the frontend."""
    parts = []
    if profile.major:
        parts.append(f"{profile.major}背景")
    if profile.interests:
        parts.append(f"研究兴趣集中在{profile.interests}")
    if profile.projects:
        parts.append(f"已有项目经历：{profile.projects}")
    target = "、".join(x for x in [profile.target_schools, profile.target_colleges] if x)
    if target:
        parts.append(f"目标范围：{target}")
    if not parts:
        return "请先补充本科专业、研究兴趣、项目经历和目标院校，系统将生成申请画像摘要。"
    return "；".join(parts) + "。"


def extract_supervisors_from_text(text: str, source: str = "用户上传资料", start_id: int = 1) -> list[Supervisor]:
    """
    Extract supervisor records from pasted text.

    The tool supports two lightweight formats for the course prototype:
    1. CSV/TSV text with headers such as 姓名, 学校, 学院, 研究方向, 邮箱.
    2. Free text blocks separated by blank lines.
    """
    text = (text or "").strip()
    if not text:
        return []

    csv_records = _try_parse_table(text, source, start_id)
    if csv_records:
        return csv_records

    blocks = [b.strip() for b in re.split(r"\n\s*\n|[-=]{3,}", text) if b.strip()]
    if len(blocks) == 1 and len(text) > 260:
        blocks = [line.strip() for line in text.splitlines() if line.strip()]

    supervisors: list[Supervisor] = []
    for offset, block in enumerate(blocks):
        supervisors.append(_parse_free_text_block(block, source, start_id + offset))
    return supervisors


def score_supervisor_match(profile: StudentProfile, supervisor: Supervisor) -> Supervisor:
    """
    Score one supervisor against a student profile.

    Weights follow the project design:
    research direction 40%, admission type 20%, school/college preference 15%,
    project relevance 15%, information completeness/risk 10%.
    """
    interests = _tokens(profile.interests)
    projects = _tokens(profile.projects)
    targets = _tokens(profile.target_schools + " " + profile.target_colleges)
    direction = _tokens(supervisor.direction)
    admission = _tokens(supervisor.admission_type)
    identity = _tokens(supervisor.school + " " + supervisor.college)

    direction_score = _overlap_score(interests, direction) * 40
    admission_score = _overlap_score(_tokens(profile.application_type), admission) * 20
    target_score = _overlap_score(targets, identity) * 15
    project_score = _overlap_score(projects, direction) * 15
    completeness_score = _completeness_score(supervisor) * 10

    score = round(direction_score + admission_score + target_score + project_score + completeness_score)
    score = max(0, min(100, score))

    supervisor.match_score = score
    supervisor.match_level = _level(score)
    supervisor.match_reason = _match_reason(profile, supervisor, {
        "direction": direction_score,
        "admission": admission_score,
        "target": target_score,
        "project": project_score,
        "completeness": completeness_score,
    })
    supervisor.risk_note = _risk_note(supervisor)
    return supervisor


def score_supervisors_hybrid(profile: StudentProfile, supervisors: Iterable[Supervisor]) -> list[Supervisor]:
    """Hybrid ranker: TF-IDF text vectors plus structured application constraints.

    It runs locally with the Python standard library, so matching remains available
    when an embedding API or external model is unavailable. The agent can then use
    an LLM only as a constrained second-stage re-ranker over these real candidates.
    """
    items = list(supervisors)
    if not items:
        return []
    query = " ".join([profile.major, profile.interests, profile.projects, profile.application_type])
    documents = [query] + [_supervisor_match_text(item) for item in items]
    vectors = _tfidf_vectors(documents)
    query_vector = vectors[0]
    interests = _tokens(profile.interests)
    projects = _tokens(profile.projects)
    targets = _tokens(profile.target_schools + " " + profile.target_colleges)
    application = _tokens(profile.application_type)

    for index, supervisor in enumerate(items, start=1):
        direction = _tokens(supervisor.direction)
        admission = _tokens(supervisor.admission_type)
        identity = _tokens(supervisor.school + " " + supervisor.college)
        text_score = _cosine_similarity(query_vector, vectors[index]) * 100
        direction_score = _overlap_score(interests, direction) * 100
        project_score = _overlap_score(projects, direction) * 100
        admission_score = _overlap_score(application, admission) * 100
        target_score = _overlap_score(targets, identity) * 100
        quality_score = _completeness_score(supervisor) * 100
        final_score = round(
            0.45 * text_score
            + 0.15 * direction_score
            + 0.10 * project_score
            + 0.10 * admission_score
            + 0.10 * target_score
            + 0.10 * quality_score
        )
        supervisor.match_score = max(0, min(100, final_score))
        supervisor.match_level = _level(supervisor.match_score)
        supervisor.match_breakdown = {
            "text_vector": round(text_score, 1),
            "direction_overlap": round(direction_score, 1),
            "project_relevance": round(project_score, 1),
            "admission_fit": round(admission_score, 1),
            "target_preference": round(target_score, 1),
            "data_quality": round(quality_score, 1),
        }
        supervisor.ranking_method = "hybrid_tfidf_rules"
        supervisor.match_reason = _hybrid_match_reason(profile, supervisor)
        supervisor.risk_note = _risk_note(supervisor)
    return sorted(items, key=lambda item: item.match_score, reverse=True)


def mmr_rerank(supervisors: Iterable[Supervisor], limit: int = 3, diversity_weight: float = 0.75) -> list[Supervisor]:
    """Maximal Marginal Relevance re-ranking for diverse top-N recommendations."""
    pool = sorted(list(supervisors), key=lambda item: item.match_score, reverse=True)
    if not pool or limit <= 0:
        return []
    vectors = _tfidf_vectors([_supervisor_match_text(item) for item in pool])
    selected_indexes: list[int] = []
    remaining = set(range(len(pool)))
    while remaining and len(selected_indexes) < limit:
        if not selected_indexes:
            choice = max(remaining, key=lambda item: pool[item].match_score)
        else:
            def mmr_value(item: int) -> float:
                relevance = pool[item].match_score / 100
                redundancy = max(_cosine_similarity(vectors[item], vectors[chosen]) for chosen in selected_indexes)
                return diversity_weight * relevance - (1 - diversity_weight) * redundancy
            choice = max(remaining, key=mmr_value)
        selected_indexes.append(choice)
        remaining.remove(choice)
    return [pool[index] for index in selected_indexes]


def generate_email_draft(profile: StudentProfile, supervisor: Supervisor, tone: str = "正式版") -> dict[str, str]:
    """Create a conservative first-contact email draft for one supervisor."""
    student_name = profile.name or "同学"
    title = supervisor.title or "老师"
    subject_direction = supervisor.direction or "您的研究方向"
    subject = f"{profile.application_type or '研究生申请'}咨询 - {student_name}"

    intro_bits = []
    if profile.university or profile.major:
        intro_bits.append(f"我是{profile.university}{profile.major}专业的{student_name}")
    else:
        intro_bits.append(f"我是{student_name}")
    if profile.rank:
        intro_bits.append(f"目前成绩排名为{profile.rank}")
    if profile.english:
        intro_bits.append(f"英语水平为{profile.english}")

    project_line = f"我曾参与{profile.projects}等相关项目。" if profile.projects else "我正在整理与申请方向相关的课程和项目经历。"
    interest_line = (
        f"我关注到您在{subject_direction}方面的工作，与我目前关注的{profile.interests or '研究兴趣'}较为契合。"
        if supervisor.direction
        else f"我对{profile.interests or '相关研究方向'}很感兴趣，希望进一步了解您的招生安排。"
    )
    attach_line = "随信附上个人简历和成绩单，供您参考。"

    body = "\n".join([
        f"{supervisor.name}{title}：",
        "",
        "您好！",
        "",
        "，".join(intro_bits) + "。"
        f"我计划申请{profile.application_type or '研究生'}，目标方向包括{profile.interests or '人工智能与软件工程相关方向'}。",
        interest_line,
        project_line,
        "",
        "想向您请教今年是否有招收相关方向学生的计划，以及我目前的背景是否适合继续准备您的课题组申请。",
        attach_line,
        "",
        "感谢您在百忙之中阅读这封邮件，期待您的回复。",
        "",
        "此致",
        "敬礼！",
        "",
        student_name,
    ])

    if tone == "简洁版":
        body = "\n".join([
            f"{supervisor.name}{title}：",
            "",
            "您好！",
            "",
            f"我是{profile.university}{profile.major}专业的{student_name}，计划申请{profile.application_type or '研究生'}。"
            f"我对{profile.interests or '相关研究方向'}感兴趣，关注到您在{subject_direction}方面的研究，希望咨询今年是否有招生计划。",
            "",
            "随信附上个人简历和成绩单，感谢您的阅读，期待您的回复。",
            "",
            f"{student_name}",
        ])

    return {"subject": subject, "body": body}


def review_email_draft(profile: StudentProfile, supervisor: Supervisor, subject: str, body: str) -> dict[str, Any]:
    """Review a draft against the project design checklist."""
    normalized_body = body.lower().replace(" ", "")
    checks = [
        {
            "label": "称呼是否规范",
            "passed": bool(supervisor.name and supervisor.name in body and ("老师" in body or supervisor.title in body)),
        },
        {
            "label": "是否针对导师方向",
            "passed": bool(supervisor.direction and any(part.lower().replace(" ", "") in normalized_body for part in _tokens(supervisor.direction))),
        },
        {
            "label": "是否说明个人背景",
            "passed": bool((profile.major and profile.major in body) or (profile.projects and profile.projects[:4] in body)),
        },
        {
            "label": "是否说明附件",
            "passed": "附件" in body or "简历" in body or "成绩单" in body,
        },
        {
            "label": "主题是否明确",
            "passed": bool(subject and ("申请" in subject or "咨询" in subject)),
        },
    ]
    passed_count = sum(1 for item in checks if item["passed"])
    suggestions = []
    if not supervisor.email:
        suggestions.append("导师邮箱缺失，确认发送前需要补充邮箱。")
    if not checks[1]["passed"]:
        suggestions.append("建议加入导师具体研究方向，降低模板感。")
    if len(body) > 1200:
        suggestions.append("正文偏长，可以压缩项目描述。")
    if not suggestions:
        suggestions.append("草稿结构完整，可以预览后再确认发送。")
    return {
        "score": round(passed_count / len(checks) * 100),
        "checks": checks,
        "suggestions": suggestions,
    }


def supervisor_to_dict(supervisor: Supervisor) -> dict[str, Any]:
    return asdict(supervisor)


def supervisor_from_dict(data: dict[str, Any]) -> Supervisor:
    allowed = Supervisor.__dataclass_fields__.keys()
    return Supervisor(**{k: v for k, v in data.items() if k in allowed})


def profile_from_dict(data: dict[str, Any]) -> StudentProfile:
    allowed = StudentProfile.__dataclass_fields__.keys()
    return StudentProfile(**{k: str(v) for k, v in data.items() if k in allowed})


def _try_parse_table(text: str, source: str, start_id: int) -> list[Supervisor]:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    delimiter = "\t" if "\t" in first_line else ","
    if delimiter not in first_line:
        return []

    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            return []
        normalized_rows = []
        for row in reader:
            normalized: dict[str, str] = {}
            for key, aliases in FIELD_ALIASES.items():
                normalized[key] = _get_alias_value(row, aliases)
            if any(normalized.values()):
                normalized_rows.append(normalized)
        supervisors = []
        for offset, row in enumerate(normalized_rows):
            supervisors.append(Supervisor(
                id=start_id + offset,
                name=row.get("name") or "待确认导师",
                school=row.get("school", ""),
                college=row.get("college", ""),
                title=row.get("title", ""),
                direction=row.get("direction", ""),
                email=row.get("email", ""),
                admission_type=row.get("admission_type", ""),
                source=row.get("source") or source,
                raw_text=str(row),
            ))
        return supervisors
    except csv.Error:
        return []


def _parse_free_text_block(block: str, source: str, item_id: int) -> Supervisor:
    email_match = EMAIL_RE.search(block)
    title_match = TITLE_RE.search(block)
    name_match = NAME_RE.search(block)

    name = name_match.group(1) if name_match else _extract_labeled(block, ["姓名", "导师", "老师"])
    title = title_match.group(1) if title_match else _extract_labeled(block, ["职称", "职位"])

    return Supervisor(
        id=item_id,
        name=name or "待确认导师",
        school=_extract_labeled(block, ["学校", "院校"]),
        college=_extract_labeled(block, ["学院", "院系", "单位"]),
        title=title,
        direction=_extract_labeled(block, ["研究方向", "方向", "领域"]) or _guess_direction(block),
        email=email_match.group(0) if email_match else "",
        admission_type=_extract_labeled(block, ["招生类型", "招生", "类型"]),
        source=source,
        raw_text=block,
    )


def _extract_labeled(text: str, labels: list[str]) -> str:
    for label in labels:
        pattern = rf"{label}\s*[:：]\s*([^\n；;，,]+)"
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def _guess_direction(text: str) -> str:
    keywords = [
        "可信AI", "可信 AI", "人工智能", "机器学习", "深度学习", "联邦学习",
        "隐私计算", "计算机视觉", "自然语言处理", "大模型", "数据挖掘", "软件工程",
        "网络安全", "图神经网络", "机器人", "智能系统",
    ]
    found = [kw for kw in keywords if kw.lower().replace(" ", "") in text.lower().replace(" ", "")]
    return "、".join(dict.fromkeys(found))


def _get_alias_value(row: dict[str, Any], aliases: list[str]) -> str:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for alias in aliases:
        value = row.get(alias)
        if value:
            return str(value).strip()
        value = lowered.get(alias.lower())
        if value:
            return str(value).strip()
    return ""


def _tokens(text: str) -> set[str]:
    raw = re.split(r"[\s,，、;；/|]+", (text or "").lower())
    tokens = {x.strip() for x in raw if len(x.strip()) >= 2}
    compact = (text or "").lower().replace(" ", "")
    domain_terms = [
        "可信ai", "人工智能", "机器学习", "深度学习", "联邦学习", "隐私计算",
        "计算机视觉", "自然语言处理", "大模型", "数据挖掘", "软件工程", "网络安全",
        "保研", "考研", "夏令营", "推免", "统考", "专硕", "学硕",
    ]
    tokens.update(term for term in domain_terms if term in compact)
    return tokens


def _supervisor_match_text(supervisor: Supervisor) -> str:
    return " ".join([
        supervisor.title,
        supervisor.direction,
        supervisor.admission_type,
        supervisor.school,
        supervisor.college,
        supervisor.raw_text[:800],
    ])


def _character_ngrams(text: str) -> Counter[str]:
    compact = re.sub(r"\s+", "", (text or "").lower())
    grams: Counter[str] = Counter()
    for size in (2, 3, 4):
        for index in range(max(0, len(compact) - size + 1)):
            gram = compact[index:index + size]
            if gram.strip():
                grams[gram] += 1
    for token in _tokens(text):
        grams[f"token:{token}"] += 2
    return grams


def _tfidf_vectors(documents: list[str]) -> list[dict[str, float]]:
    counters = [_character_ngrams(document) for document in documents]
    document_frequency: Counter[str] = Counter()
    for counter in counters:
        document_frequency.update(counter.keys())
    total = len(counters)
    vectors: list[dict[str, float]] = []
    for counter in counters:
        total_terms = sum(counter.values()) or 1
        vector = {
            term: (count / total_terms) * (math.log((total + 1) / (document_frequency[term] + 1)) + 1)
            for term, count in counter.items()
        }
        vectors.append(vector)
    return vectors


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    numerator = sum(value * right.get(term, 0.0) for term, value in left.items())
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    matched = left.intersection(right)
    if matched:
        return min(1.0, len(matched) / max(1, min(len(left), 3)))
    return 0.0


def _hybrid_match_reason(profile: StudentProfile, supervisor: Supervisor) -> str:
    parts = supervisor.match_breakdown
    reasons = [f"文本向量相似度 {parts.get('text_vector', 0):.0f}/100"]
    if parts.get("direction_overlap", 0) > 0:
        reasons.append(f"研究方向与「{profile.interests}」存在关键词重合")
    if parts.get("project_relevance", 0) > 0:
        reasons.append("项目经历与导师方向存在关联")
    if parts.get("target_preference", 0) > 0:
        reasons.append("目标院校或学院偏好匹配")
    if parts.get("data_quality", 0) < 70:
        reasons.append("资料字段不完整，已降低排序权重")
    return "；".join(reasons) + "。"


def _completeness_score(supervisor: Supervisor) -> float:
    fields = [supervisor.name, supervisor.school, supervisor.college, supervisor.direction, supervisor.email, supervisor.source]
    return sum(1 for field in fields if field and field != "待确认导师") / len(fields)


def _level(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def _match_reason(profile: StudentProfile, supervisor: Supervisor, parts: dict[str, float]) -> str:
    reasons = []
    if parts["direction"] > 0:
        reasons.append(f"研究方向与「{profile.interests}」存在重合")
    if parts["project"] > 0:
        reasons.append("学生项目经历可支撑相关方向沟通")
    if parts["admission"] > 0:
        reasons.append(f"招生类型与「{profile.application_type}」匹配")
    if parts["target"] > 0:
        reasons.append("院校或学院偏好匹配")
    if supervisor.email:
        reasons.append("邮箱信息完整，便于后续联系")
    return "；".join(reasons) + "。" if reasons else "当前资料与学生画像重合有限，建议补充导师方向或学生项目细节后重新评分。"


def _risk_note(supervisor: Supervisor) -> str:
    risks = []
    if not supervisor.email:
        risks.append("缺少邮箱")
    if not supervisor.direction:
        risks.append("缺少明确研究方向")
    if not supervisor.admission_type:
        risks.append("未说明招生类型")
    if supervisor.source in {"", "用户上传资料"}:
        risks.append("来源需要进一步标注")
    if not risks:
        return "暂无明显信息缺口，仍建议以学院官网最新通知为准。"
    return "；".join(risks) + "，建议人工核验。"
