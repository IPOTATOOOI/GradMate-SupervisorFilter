from __future__ import annotations

import json
import logging
import re
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

from agent_tools import extract_supervisors_from_text, supervisor_to_dict
from config import WORK_ROOT, get_browser_settings, get_model_settings
from school_directory import find_school_sites
from storage import get_supervisors, merge_supervisors, save_supervisors


TEACHER_LINK_KEYWORDS = ["导师", "教师", "师资", "队伍", "团队", "人员", "研究所", "实验室", "faculty", "teacher"]
TITLE_KEYWORDS = ["教授", "副教授", "讲师", "研究员", "副研究员", "博士生导师", "硕士生导师", "博导", "硕导"]
BAD_NAME_VALUES = {"待确认导师", "讲席", "教授", "导师", "教师", "博士", "硕士", "主任", "学院", "团队"}
SEARCH_LINK_BLOCKLIST = ["baidu.com", "google.com", "duckduckgo.com", "microsoft.com", "javascript:"]
GENERIC_EMAIL_LOCAL_PARTS = {"admin", "office", "info", "contact", "service", "webmaster", "csdean", "dean", "secretary"}
_BROWSER_RESEARCH_LOCK = Lock()
_BROWSER_PROGRESS_CALLBACK: ContextVar[Any | None] = ContextVar("browser_progress_callback", default=None)
logger = logging.getLogger(__name__)


@dataclass
class BrowserPage:
    title: str
    url: str
    text: str


def _log(message: str) -> None:
    logger.info("Browser research: %s", message)


@contextmanager
def browser_progress(callback):
    """Expose browser progress to the SSE controller without changing tool schema."""
    token = _BROWSER_PROGRESS_CALLBACK.set(callback)
    try:
        yield
    finally:
        _BROWSER_PROGRESS_CALLBACK.reset(token)


def _ensure_selenium() -> Any:
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
    except ImportError as error:
        raise RuntimeError("当前 Python 环境未安装 selenium，请先执行：pip install selenium") from error
    return webdriver, Options, Service, By, WebDriverWait


def _create_driver():
    webdriver, Options, Service, _, _ = _ensure_selenium()
    settings = get_browser_settings()

    options = Options()
    if settings.headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--window-size=1440,1100")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    profile_root = WORK_ROOT / "browser_profiles"
    profile_root.mkdir(parents=True, exist_ok=True)
    options.add_argument("--remote-debugging-port=0")
    options.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='gradmate_chrome_', dir=str(profile_root))}")
    options.add_argument("--lang=zh-CN")
    options.add_argument("--ignore-certificate-errors")
    if settings.chrome_binary_path:
        options.binary_location = str(settings.chrome_binary_path)

    if settings.chromedriver_path:
        if not settings.chromedriver_path.exists():
            raise RuntimeError(f"未找到 CHROMEDRIVER_PATH 指定的驱动：{settings.chromedriver_path}")
        return webdriver.Chrome(service=Service(str(settings.chromedriver_path)), options=options)
    # Selenium 4 can resolve a compatible driver through Selenium Manager.
    return webdriver.Chrome(options=options)


def _search_queries(school: str, major: str, college: str, keywords: str) -> list[str]:
    base = " ".join(part for part in [school, college or major] if part).strip()
    suffixes = ["导师", "师资队伍", "教师名录", "研究生导师", "教师个人主页", "学院 官网"]
    if keywords:
        suffixes.insert(0, keywords)
    return [f"{base} {suffix}".strip() for suffix in suffixes if base]


def _is_candidate_url(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    parsed = urlparse(url)
    if "bing.com" in parsed.netloc.lower():
        return parsed.path.startswith("/ck/a")
    lowered = url.lower()
    return not any(blocked in lowered for blocked in SEARCH_LINK_BLOCKLIST)


def _normalize_search_href(href: str) -> str:
    parsed = urlparse(href)
    host = parsed.netloc.lower()
    if "duckduckgo.com" in host and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def _score_link(text: str, url: str, school: str, major: str, college: str) -> int:
    merged = f"{text} {url}".lower()
    score = 0
    for keyword in TEACHER_LINK_KEYWORDS:
        if keyword.lower() in merged:
            score += 8
    for keyword in [school, major, college]:
        if keyword and keyword.lower() in merged:
            score += 5
    if ".edu.cn" in merged or ".edu." in merged:
        score += 6
    if "news." in merged or "/news" in merged:
        score -= 10
    if any(word in merged for word in ["招生", "通知", "公告", "就业", "新闻"]):
        score -= 3
    if "teacher" in merged or "faculty" in merged or "/info/" in merged:
        score += 5
    return score


def _collect_links(driver, by, school: str, major: str, college: str, limit: int) -> list[dict[str, Any]]:
    links = []
    fallback_links = []
    result_elements = driver.find_elements(by.CSS_SELECTOR, "li.b_algo h2 a, .b_algo a")
    elements = result_elements or driver.find_elements(by.TAG_NAME, "a")
    for element in elements:
        try:
            text = (element.text or "").strip()
            href = _normalize_search_href((element.get_attribute("href") or "").strip())
        except Exception:
            continue
        if not _is_candidate_url(href):
            continue
        score = _score_link(text, href, school, major, college)
        if score <= 0:
            if ".edu.cn" in href.lower() or ".edu." in href.lower():
                fallback_links.append({"text": text[:120], "url": href, "score": 1})
            continue
        links.append({"text": text[:120], "url": href, "score": score})
    if not links:
        links = fallback_links[:limit]

    deduped: dict[str, dict[str, Any]] = {}
    for item in links:
        parsed = urlparse(item["url"])
        key = f"{parsed.netloc}{parsed.path}".rstrip("/")
        if key not in deduped or item["score"] > deduped[key]["score"]:
            deduped[key] = item
    return sorted(deduped.values(), key=lambda item: item["score"], reverse=True)[:limit]


def _page_text(driver, by, wait, url: str) -> BrowserPage:
    driver.get(url)
    wait(driver, 10).until(lambda item: item.execute_script("return document.readyState") in {"interactive", "complete"})
    title = driver.title or ""
    if any(host in urlparse(driver.current_url).netloc.lower() for host in ["bing.com", "duckduckgo.com", "google.com"]):
        raise RuntimeError("搜索引擎导航页已跳过")
    body = driver.find_element(by.TAG_NAME, "body")
    text = re.sub(r"\n{3,}", "\n\n", body.text or "").strip()
    return BrowserPage(title=title, url=driver.current_url, text=text[:30000])


def _collect_page_link_options(driver, by, limit: int = 100) -> list[dict[str, str]]:
    options = []
    for element in driver.find_elements(by.TAG_NAME, "a"):
        try:
            text = (element.text or "").strip()
            href = (element.get_attribute("href") or "").strip()
        except Exception:
            continue
        if not href.startswith(("http://", "https://")):
            continue
        if not text and not any(marker in href.lower() for marker in ["info", "teacher", "faculty", "szdw", "szzk"]):
            continue
        label = text[:120]
        if not label and "/info/" in href.lower():
            label = "疑似教师详情页"
        options.append({"text": label, "url": href})

    deduped = []
    seen = set()
    for item in options:
        key = item["url"].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    deduped.sort(key=lambda item: ("/info/" not in item["url"].lower(), item["url"]))
    return deduped[:limit]


def _collect_related_links(driver, by, current_url: str, limit: int = 3) -> list[str]:
    current_host = urlparse(current_url).netloc
    candidates: list[tuple[int, str]] = []
    for element in driver.find_elements(by.TAG_NAME, "a"):
        try:
            text = (element.text or "").strip()
            href = (element.get_attribute("href") or "").strip()
        except Exception:
            continue
        if not href.startswith(("http://", "https://")):
            continue
        if urlparse(href).netloc != current_host:
            continue
        path = urlparse(href).path.lower()
        score = _score_link(text, href, "", "", "")
        is_teacher_detail = "/info/" in path and any(marker in current_url.lower() for marker in ["/szzk/", "/szdw/", "teacher", "faculty"])
        if score > 0 or is_teacher_detail:
            if is_teacher_detail:
                score += 50
            if text and any(keyword in text for keyword in TITLE_KEYWORDS):
                score += 20
            candidates.append((score, href))
    sorted_urls = [url for _, url in sorted(candidates, key=lambda item: item[0], reverse=True)]
    return list(dict.fromkeys(sorted_urls))[:limit]


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


def _make_chat_model():
    model_settings = get_model_settings()
    if not model_settings.configured:
        return None
    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        return None
    return ChatOpenAI(
        model=model_settings.model_id,
        api_key=model_settings.api_key,
        base_url=model_settings.base_url,
        temperature=0,
        timeout=model_settings.timeout_seconds,
        max_retries=0,
        max_tokens=1800,
    )


def _llm_pick_links(page: BrowserPage, options: list[dict[str, str]], limit: int, trace_log) -> list[str]:
    settings = get_browser_settings()
    if not settings.llm_assist or not options:
        trace_log("大模型辅助点击：已关闭或没有候选链接，使用规则链接选择")
        return []
    model = _make_chat_model()
    if model is None:
        trace_log("大模型辅助点击：模型未配置或不可用，使用规则链接选择")
        return []

    compact_options = [{"index": index, "text": item["text"], "url": item["url"]} for index, item in enumerate(options[:70])]
    prompt = f"""
你是 GradMate 的网页浏览助手。当前任务是从学校/学院网页中继续点击最可能包含导师个人信息的链接。

当前页面标题：{page.title}
当前页面 URL：{page.url}
当前页面正文摘要：
{page.text[:1800]}

候选链接 JSON：
{json.dumps(compact_options, ensure_ascii=False)}

请选择最多 {limit} 个最值得点击的链接。优先级：
1. 教师个人主页、导师详情页、教职工详情页。
2. 师资队伍、教师名录、导师目录。
3. 研究所/实验室里可能列出教师的页面。

不要选择新闻、招生通知、首页、英文首页、地图、登录、搜索、图片、附件下载。
只返回 JSON，格式：{{"indexes":[0,1],"reason":"简短理由"}}
"""
    try:
        response = model.invoke(prompt)
        data = _extract_json_object(getattr(response, "content", str(response)))
        indexes = data.get("indexes", [])
        if not isinstance(indexes, list):
            indexes = []
        urls = []
        for index in indexes:
            if isinstance(index, int) and 0 <= index < len(options):
                urls.append(options[index]["url"])
        reason = str(data.get("reason") or "").strip()
        trace_log(f"大模型辅助点击：选择 {len(urls)} 个链接；理由：{reason[:120] or '无'}")
        return list(dict.fromkeys(urls))[:limit]
    except Exception as error:
        trace_log(f"大模型辅助点击失败，使用规则链接选择：{error}")
        return []


def _is_valid_supervisor_record(data: dict[str, Any]) -> bool:
    name = str(data.get("name") or "").strip()
    if not name or name in BAD_NAME_VALUES or "大学" in name or "学院" in name or "学校" in name:
        return False
    if len(name) < 2 or len(name) > 8:
        return False
    direction = str(data.get("direction") or "").strip()
    email = str(data.get("email") or "").strip()
    local_part = email.split("@", 1)[0].lower() if "@" in email else ""
    personal_email = bool(email and local_part and local_part not in GENERIC_EMAIL_LOCAL_PARTS)
    return bool(direction or personal_email)


def _normalize_llm_record(record: dict[str, Any], page: BrowserPage, school: str, college: str, item_id: int) -> dict[str, Any] | None:
    name = str(record.get("name") or "").strip()
    title = str(record.get("title") or "").strip()
    direction = str(record.get("direction") or "").strip()
    email = str(record.get("email") or "").strip()
    evidence = str(record.get("evidence") or "").strip()

    if email and email not in page.text:
        email = ""
    if direction and len(direction) > 180:
        direction = direction[:180]
    if title and len(title) > 24:
        title = ""

    data = {
        "id": item_id,
        "name": name,
        "school": str(record.get("school") or school).strip(),
        "college": str(record.get("college") or college).strip(),
        "title": title,
        "direction": direction,
        "email": email,
        "admission_type": str(record.get("admission_type") or "").strip(),
        "source": str(record.get("source") or page.url).strip(),
        "raw_text": evidence[:1000] or page.text[:1000],
        "match_score": 0,
        "match_level": "未评估",
        "match_reason": "",
        "risk_note": "",
    }
    return data if _is_valid_supervisor_record(data) else None


def _llm_extract_supervisors_from_page(page: BrowserPage, school: str, college: str, start_id: int, trace_log) -> list[dict[str, Any]]:
    settings = get_browser_settings()
    if not settings.llm_extract:
        trace_log("大模型页面抽取：已关闭，使用规则抽取")
        return []
    model = _make_chat_model()
    if model is None:
        trace_log("大模型页面抽取：模型未配置或不可用，使用规则抽取")
        return []

    page_excerpt = page.text[:settings.llm_page_text_limit]
    prompt = f"""
Hard constraints: return at most {settings.llm_extract_max_records} records. Every record must contain a real person's name plus a specific research direction or a personal email evidenced by this page. Do not return department mailboxes, public mailboxes, university names, honorary-title lists, news authors, or navigation labels.

你是 GradMate 的导师信息抽取器。请只根据当前网页文本抽取导师信息，不要猜测，不要补全网页中没有的信息。

当前学校：{school}
当前院系/专业：{college}
页面标题：{page.title}
页面 URL：{page.url}

网页文本：
{page_excerpt}

抽取规则：
1. 只抽取网页中明确出现的教师/导师/研究员个人信息。
2. 姓名、邮箱、研究方向必须属于同一个教师；如果不能确认邮箱属于该教师，email 留空。
3. 若页面是教师详情页，通常只输出 1 条。
4. 若页面是教师列表页，可以输出多条，但每条必须有姓名，并且至少有职称、方向、邮箱之一。
5. 不要抽取新闻作者、编辑、学生、行政栏目、导航菜单、版权邮箱。
6. source 必须使用当前页面 URL。
7. evidence 填写支持该条记录的原文片段，尽量包含姓名和邮箱/职称/方向。

只返回 JSON，格式：
{{
  "supervisors": [
    {{
      "name": "姓名",
      "school": "{school}",
      "college": "{college}",
      "title": "职称",
      "direction": "研究方向",
      "email": "邮箱",
      "admission_type": "",
      "source": "{page.url}",
      "evidence": "原文片段"
    }}
  ]
}}
"""
    started_at = perf_counter()
    trace_log(
        "[LLM页面抽取开始] "
        f"title={page.title!r}; url={page.url}; page_chars={len(page.text)}; "
        f"sent_chars={len(page_excerpt)}; prompt_chars={len(prompt)}; "
        f"timeout={settings.timeout_seconds if hasattr(settings, 'timeout_seconds') else get_model_settings().timeout_seconds}s; "
        f"max_records={settings.llm_extract_max_records}"
    )
    try:
        response = model.invoke(prompt)
        content = getattr(response, "content", str(response))
        content = content if isinstance(content, str) else str(content)
        data = _extract_json_object(content)
        records = data.get("supervisors", [])
        if not isinstance(records, list):
            records = []
        raw_record_count = len(records)
        records = records[:settings.llm_extract_max_records]
        supervisors = []
        for record in records:
            if not isinstance(record, dict):
                continue
            normalized = _normalize_llm_record(record, page, school, college, start_id + len(supervisors))
            if normalized:
                supervisors.append(normalized)
        trace_log(
            "[LLM页面抽取完成] "
            f"elapsed={perf_counter() - started_at:.2f}s; response_chars={len(content)}; "
            f"raw_records={raw_record_count}; capped_records={len(records)}; valid_records={len(supervisors)}; url={page.url}"
        )
        return supervisors
    except Exception as error:
        trace_log(
            "[LLM页面抽取失败] "
            f"elapsed={perf_counter() - started_at:.2f}s; error_type={type(error).__name__}; "
            f"error={error!r}; url={page.url}; 将使用规则抽取"
        )
        return []


def _make_source(page: BrowserPage) -> str:
    return page.url or page.title or "浏览器自动检索"


def _looks_like_teacher_content(text: str) -> bool:
    if not text:
        return False
    title_hits = sum(1 for keyword in TITLE_KEYWORDS if keyword in text)
    contact_hits = len(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text))
    teacher_hits = sum(1 for keyword in TEACHER_LINK_KEYWORDS if keyword.lower() in text.lower())
    return title_hits >= 2 or contact_hits >= 2 or (teacher_hits >= 1 and title_hits >= 1)


def _extract_supervisor_snippets(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    selected: list[str] = []
    for index, line in enumerate(lines):
        if len(line) < 2 or len(line) > 260:
            continue
        has_title = any(keyword in line for keyword in TITLE_KEYWORDS)
        has_email = bool(re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", line))
        has_teacher_word = any(keyword in line for keyword in TEACHER_LINK_KEYWORDS)
        if not (has_title or has_email or has_teacher_word):
            continue
        start = max(0, index - 2)
        end = min(len(lines), index + 4)
        selected.extend(lines[start:end])
        selected.append("")
    return "\n".join(dict.fromkeys(selected)).strip()


def _extract_profile_record_from_page(page: BrowserPage, school: str, college: str, item_id: int) -> dict[str, Any] | None:
    lines = [line.strip() for line in page.text.splitlines() if line.strip()]
    title = ""
    email = ""
    direction = ""
    name = ""

    email_match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", page.text)
    if email_match:
        email = email_match.group(0)

    for line in lines[:100]:
        if not title:
            title_match = re.search(r"(?:职称|职位|职务)\s*[:：]\s*([^\s，。；;]+)", line)
            if title_match:
                title = title_match.group(1).strip()
        if not direction:
            direction_match = re.search(r"(?:研究方向|研究领域|方向)\s*[:：]\s*(.+)", line)
            if direction_match:
                direction = direction_match.group(1).strip()[:180]

    title_index = next((idx for idx, line in enumerate(lines[:100]) if any(keyword in line for keyword in TITLE_KEYWORDS)), -1)
    search_window = lines[max(0, title_index - 8): title_index] if title_index >= 0 else lines[:20]
    for line in reversed(search_window):
        clean = re.sub(r"当前位置|首页|师资|教职工名录|>", " ", line).strip()
        candidates = re.findall(r"[\u4e00-\u9fa5]{2,4}", clean)
        candidates = [item for item in candidates if item not in BAD_NAME_VALUES and item not in ["清华大学", "计算机", "科学", "技术"]]
        if candidates:
            name = candidates[-1]
            break

    if not name or not (title or email or direction):
        return None
    data = {
        "id": item_id,
        "name": name,
        "school": school,
        "college": college,
        "title": title,
        "direction": direction,
        "email": email,
        "admission_type": "",
        "source": page.url,
        "raw_text": "\n".join(lines[:100]),
        "match_score": 0,
        "match_level": "未评估",
        "match_reason": "",
        "risk_note": "",
    }
    return data if _is_valid_supervisor_record(data) else None


def _append_extracted_supervisors(pages: list[BrowserPage], school: str, college: str, trace_log=None) -> list[dict[str, Any]]:
    if trace_log is None:
        trace_log = _log
    current = get_supervisors()
    start_id = max([int(item.get("id", 0)) for item in current] + [0]) + 1
    imported = []

    settings = get_browser_settings()
    for page_index, page in enumerate(pages):
        remaining = settings.final_supervisor_limit - len(imported)
        if remaining <= 0:
            trace_log(f"[任务结果已足够] 已得到 {len(imported)} 位合格导师，停止后续页面抽取")
            break
        trace_log(
            f"[页面处理 {page_index + 1}/{len(pages)}] title={page.title!r}; "
            f"text_chars={len(page.text)}; url={page.url}"
        )
        if page_index < settings.llm_extract_max_pages:
            llm_records = _llm_extract_supervisors_from_page(page, school, college, start_id + len(imported), trace_log)
        else:
            trace_log(f"[页面跳过] 已达到 {settings.llm_extract_max_pages} 个大模型页面上限；规则抽取已禁用；url={page.url}")
            llm_records = []
        if llm_records:
            accepted_records = llm_records[:remaining]
            imported.extend(accepted_records)
            if len(llm_records) > len(accepted_records):
                trace_log(f"[结果数量限制] 本页模型返回 {len(llm_records)} 条，仅保留剩余的 {len(accepted_records)} 条")
            continue

        trace_log(f"[大模型抽取跳过] 未获得满足姓名和方向/个人邮箱条件的记录；未启用规则抽取；url={page.url}")
        continue

        profile_record = _extract_profile_record_from_page(page, school, college, start_id + len(imported))
        if profile_record:
            imported.append(profile_record)
            trace_log(f"[规则详情页抽取] 成功 1 条；url={page.url}")
            continue

        if not _looks_like_teacher_content(page.text):
            trace_log(f"[规则抽取跳过] 未检测到足够导师特征；url={page.url}")
            continue
        source = _make_source(page)
        text = _extract_supervisor_snippets(page.text)
        if not text:
            continue
        if school and school not in text[:500]:
            text = f"学校：{school}\n{text}"
        if college and college not in text[:500]:
            text = f"学院：{college}\n{text}"
        extracted = extract_supervisors_from_text(text=text, source=source, start_id=start_id + len(imported))
        valid_count = 0
        for supervisor in extracted:
            data = supervisor_to_dict(supervisor)
            if not _is_valid_supervisor_record(data):
                continue
            if not data.get("school"):
                data["school"] = school
            if college and not data.get("college"):
                data["college"] = college
            imported.append(data)
            valid_count += 1
        trace_log(f"[规则列表页抽取] 初步={len(extracted)} 条；有效={valid_count} 条；url={page.url}")

    supervisors, added = merge_supervisors(current, imported)
    save_supervisors(supervisors)
    trace_log(
        f"导师入库汇总：页面抽取有效记录 {len(imported)} 条，"
        f"去重后新增 {len(added)} 条，已存在并补全/跳过 {len(imported) - len(added)} 条，"
        f"当前导师库共 {len(supervisors)} 条。"
    )
    return added


def _browse_school_supervisors(
    school: str,
    major: str = "",
    college: str = "",
    keywords: str = "",
    max_pages: int | None = None,
    save: bool = True,
    task_id: str = "",
) -> dict[str, Any]:
    school = school.strip()
    major = major.strip()
    college = college.strip()
    keywords = keywords.strip()
    if not school or not (major or college):
        raise ValueError("请至少填写学校，以及专业或学院关键词。")

    trace: list[str] = []
    tag = f"[task={task_id}] " if task_id else ""

    def trace_log(message: str) -> None:
        tagged_message = f"{tag}{message}"
        trace.append(tagged_message)
        _log(tagged_message)
        callback = _BROWSER_PROGRESS_CALLBACK.get()
        if callback:
            try:
                callback(tagged_message)
            except Exception:
                pass

    settings = get_browser_settings()
    page_limit = max(1, min(max_pages or settings.max_pages, 30))
    webdriver, _, _, By, WebDriverWait = _ensure_selenium()
    del webdriver

    pages: list[BrowserPage] = []
    directory_sites = find_school_sites(school=school, major=major, college=college, limit=page_limit * 2)
    trace_log(f"输入：school={school}, major={major}, college={college}, max_pages={page_limit}")
    trace_log(f"Excel 官网目录匹配：{len(directory_sites)} 条")
    candidate_links: list[dict[str, Any]] = [
        {
            "text": " / ".join(part for part in [site.school, site.department, site.major] if part) or site.url,
            "url": site.url,
            "score": 100,
            "source": "school_directory",
        }
        for site in directory_sites
    ]

    visited: set[str] = set()
    driver = _create_driver()
    try:
        if not candidate_links:
            trace_log("Excel 未匹配到官网，回退搜索引擎")
            for query in _search_queries(school, major, college, keywords):
                search_url = settings.search_url_template.format(query=quote_plus(query))
                trace_log(f"搜索：{query}")
                driver.get(search_url)
                WebDriverWait(driver, 10).until(
                    lambda item: item.execute_script("return document.readyState") in {"interactive", "complete"}
                )
                candidate_links.extend(_collect_links(driver, By, school, major, college, page_limit * 2))

        candidate_links = sorted(candidate_links, key=lambda item: item["score"], reverse=True)
        trace_log(f"候选入口：{len(candidate_links)} 条")
        for link in candidate_links:
            if len(pages) >= page_limit:
                break
            url = link["url"]
            if url in visited:
                continue
            visited.add(url)
            try:
                trace_log(f"打开入口：{url}")
                page = _page_text(driver, By, WebDriverWait, url)
            except Exception as error:
                trace_log(f"入口打开失败，跳过：{url}；原因：{error}")
                continue
            pages.append(page)
            trace_log(f"入口文本长度：{len(page.text)}，标题：{page.title}")

            remaining = page_limit - len(pages)
            if remaining <= 0:
                continue
            rule_related_urls = _collect_related_links(driver, By, page.url, limit=remaining)
            llm_related_urls = _llm_pick_links(page, _collect_page_link_options(driver, By), remaining, trace_log)
            related_urls = list(dict.fromkeys(rule_related_urls + llm_related_urls))
            for related_url in related_urls:
                if len(pages) >= page_limit:
                    break
                if related_url in visited:
                    continue
                visited.add(related_url)
                try:
                    trace_log(f"打开详情/相关页：{related_url}")
                    pages.append(_page_text(driver, By, WebDriverWait, related_url))
                except Exception as error:
                    trace_log(f"详情/相关页打开失败，跳过：{related_url}；原因：{error}")
                    continue
    finally:
        driver.quit()

    imported = _append_extracted_supervisors(pages, school, college or major, trace_log) if save and pages else []
    trace_log(f"访问页面数：{len(pages)}，导入导师数：{len(imported)}")
    return {
        "school": school,
        "major": major,
        "college": college,
        "directory_matches": [
            {
                "school": site.school,
                "department": site.department,
                "major": site.major,
                "url": site.url,
                "source_sheet": site.source_sheet,
            }
            for site in directory_sites
        ],
        "visited_pages": [{"title": page.title, "url": page.url, "text_length": len(page.text)} for page in pages],
        "candidate_links": candidate_links[:10],
        "trace": trace,
        "imported": len(imported),
        # Return only this request's accepted records. The full database remains
        # available through /api/supervisors and is refreshed by the frontend.
        "supervisors": imported,
    }


def browse_school_supervisors(
    school: str,
    major: str = "",
    college: str = "",
    keywords: str = "",
    max_pages: int | None = None,
    save: bool = True,
    task_id: str = "",
) -> dict[str, Any]:
    """Run only one browser-research job at a time to avoid competing sessions."""
    if not _BROWSER_RESEARCH_LOCK.acquire(blocking=False):
        raise RuntimeError("已有导师官网检索任务正在执行，请等待其完成后再发起新的检索。")
    try:
        return _browse_school_supervisors(
            school=school,
            major=major,
            college=college,
            keywords=keywords,
            max_pages=max_pages,
            save=save,
            task_id=task_id,
        )
    finally:
        _BROWSER_RESEARCH_LOCK.release()
