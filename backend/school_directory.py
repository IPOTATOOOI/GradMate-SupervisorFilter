from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from config import get_school_directory_settings


NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
URL_RE = re.compile(r"https?://[^\s，,；;]+", re.IGNORECASE)
DOMAIN_RE = re.compile(r"([A-Za-z0-9-]+\.)+(edu\.cn|edu|cn|com|org|net)(/[^\s，,；;]*)?", re.IGNORECASE)


@dataclass(frozen=True)
class SchoolSite:
    school: str
    department: str
    major: str
    url: str
    source_sheet: str
    raw: dict[str, str]


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _cell_col(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter.upper()) - ord("A") + 1
    return number - 1


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in item.findall(".//a:t", NS)) for item in root.findall("a:si", NS)]


def _workbook_sheets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rels = {}
    for rel in rels_root:
        target = rel.attrib.get("Target", "")
        if not target.endswith(".xml"):
            continue
        target = target.lstrip("/")
        if target.startswith("../"):
            target = target.replace("../", "", 1)
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        rels[rel.attrib["Id"]] = target
    sheets = []
    for sheet in workbook.findall(".//a:sheet", NS):
        rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rels.get(rel_id or "")
        if target:
            sheets.append((sheet.attrib.get("name", ""), target))
    return sheets


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value_node = cell.find("a:v", NS)
    if cell.attrib.get("t") == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//a:t", NS)).strip()
    if value_node is None:
        return ""
    value = value_node.text or ""
    if cell.attrib.get("t") == "s" and value:
        return shared_strings[int(value)].strip()
    return value.strip()


def _read_rows(zf: zipfile.ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[str]]:
    root = ET.fromstring(zf.read(sheet_path))
    rows: list[list[str]] = []
    for row in root.findall(".//a:sheetData/a:row", NS):
        values: dict[int, str] = {}
        for cell in row.findall("a:c", NS):
            ref = cell.attrib.get("r", "")
            values[_cell_col(ref)] = _cell_value(cell, shared_strings)
        if values:
            max_col = max(values)
            rows.append([values.get(index, "") for index in range(max_col + 1)])
    return rows


def _read_sheet_hyperlinks(zf: zipfile.ZipFile, sheet_path: str) -> dict[str, str]:
    rel_path = sheet_path.replace("worksheets/", "worksheets/_rels/") + ".rels"
    if rel_path not in zf.namelist():
        return {}
    rel_root = ET.fromstring(zf.read(rel_path))
    rels = {rel.attrib.get("Id", ""): rel.attrib.get("Target", "") for rel in rel_root}
    root = ET.fromstring(zf.read(sheet_path))
    links: dict[str, str] = {}
    for link in root.findall(".//a:hyperlink", NS):
        ref = link.attrib.get("ref", "")
        rel_id = link.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
        target = rels.get(rel_id, "")
        if ref and target:
            links[ref] = target
    return links


def _first_present(row: dict[str, str], keywords: list[str]) -> str:
    for key, value in row.items():
        compact_key = _compact(key)
        if any(keyword in compact_key for keyword in keywords) and value:
            return value.strip()
    return ""


def _extract_url(row: dict[str, str]) -> str:
    teacher_url = _first_present(row, ["导师", "教师", "师资"])
    if teacher_url:
        match = URL_RE.search(teacher_url)
        if match:
            return match.group(0)
        domain = DOMAIN_RE.search(teacher_url)
        if domain:
            value = domain.group(0)
            return value if value.startswith(("http://", "https://")) else f"https://{value}"
    direct = _first_present(row, ["url", "网址", "官网", "链接", "website"])
    if direct:
        match = URL_RE.search(direct)
        if match:
            return match.group(0)
        domain = DOMAIN_RE.search(direct)
        if domain:
            value = domain.group(0)
            return value if value.startswith(("http://", "https://")) else f"https://{value}"
    for value in row.values():
        match = URL_RE.search(value or "")
        if match:
            return match.group(0)
        domain = DOMAIN_RE.search(value or "")
        if domain:
            value = domain.group(0)
            return value if value.startswith(("http://", "https://")) else f"https://{value}"
    return ""


def _row_to_site(row: dict[str, str], source_sheet: str) -> SchoolSite | None:
    url = _extract_url(row)
    if not url:
        return None
    school = _first_present(row, ["学校", "高校", "院校", "school", "university", "name"])
    department = _first_present(row, ["院系", "学院", "系", "department", "college"])
    major = _first_present(row, ["专业", "学科", "方向", "major", "subject"])
    if not school and not department:
        return None
    return SchoolSite(
        school=school,
        department=department,
        major=major,
        url=url,
        source_sheet=source_sheet,
        raw=row,
    )


def _header_score(row: list[str]) -> int:
    merged = _compact(" ".join(row))
    score = 0
    for keyword in ["学校", "高校", "院校", "school", "院系", "学院", "官网", "网址", "链接", "url", "教师", "导师", "师资"]:
        if keyword in merged:
            score += 1
    return score


def _headers_for_rows(rows: list[list[str]]) -> tuple[int, list[str]]:
    best_index = 0
    best_score = -1
    for index, row in enumerate(rows[:12]):
        score = _header_score(row)
        if score > best_score:
            best_index = index
            best_score = score
    headers = [item.strip() or f"列{index + 1}" for index, item in enumerate(rows[best_index])]
    # The provided GradMate Top40 workbook has a title and note before this fixed table.
    # If the text was created/opened with a non-UTF console, keyword scoring may be weak,
    # so use the URL-bearing column layout as a fallback.
    if best_score <= 1 and len(headers) >= 5:
        headers = ["排名", "学校", "院系", "院系官网", "导师目录", "状态", "备注", "数据来源"][: len(headers)]
        best_index = 2 if len(rows) > 3 else best_index
    return best_index, headers


@lru_cache(maxsize=2)
def load_school_directory(file_path: str | None = None) -> list[SchoolSite]:
    path = Path(file_path) if file_path else get_school_directory_settings().file_path
    if not path.exists():
        return []
    sites: list[SchoolSite] = []
    with zipfile.ZipFile(path) as zf:
        shared_strings = _read_shared_strings(zf)
        for sheet_name, sheet_path in _workbook_sheets(zf):
            rows = _read_rows(zf, sheet_path, shared_strings)
            hyperlinks = _read_sheet_hyperlinks(zf, sheet_path)
            if len(rows) < 2:
                continue
            header_index, headers = _headers_for_rows(rows)
            for row_offset, values in enumerate(rows[header_index + 1 :], start=header_index + 2):
                row = {
                    headers[index]: values[index].strip()
                    for index in range(min(len(headers), len(values)))
                    if values[index].strip()
                }
                for index, header in enumerate(headers[: len(values)]):
                    col_letter = ""
                    n = index + 1
                    while n:
                        n, remainder = divmod(n - 1, 26)
                        col_letter = chr(65 + remainder) + col_letter
                    target = hyperlinks.get(f"{col_letter}{row_offset}")
                    if target and not row.get(header):
                        row[header] = target
                    elif target:
                        row[header] = f"{row[header]} {target}"
                site = _row_to_site(row, sheet_name)
                if site:
                    sites.append(site)
    return sites


def find_school_sites(school: str, major: str = "", college: str = "", limit: int = 8) -> list[SchoolSite]:
    school_key = _compact(school)
    major_key = _compact(major)
    college_key = _compact(college)
    scored: list[tuple[int, SchoolSite]] = []
    for site in load_school_directory():
        merged = _compact(" ".join([site.school, site.department, site.major, site.url]))
        score = 0
        if school_key:
            if school_key in merged or merged in school_key:
                score += 10
            else:
                continue
        if not school_key and not (major_key or college_key):
            continue
        if not school_key and (major_key or college_key):
            score += 1
        if college_key and college_key in merged:
            score += 6
        if major_key and major_key in merged:
            score += 5
        if score:
            scored.append((score, site))
    deduped: dict[str, tuple[int, SchoolSite]] = {}
    for score, site in scored:
        key = site.url.rstrip("/")
        if key not in deduped or score > deduped[key][0]:
            deduped[key] = (score, site)
    return [site for _, site in sorted(deduped.values(), key=lambda item: item[0], reverse=True)[:limit]]


def school_directory_summary() -> dict[str, Any]:
    sites = load_school_directory()
    return {
        "count": len(sites),
        "items": [
            {
                "school": site.school,
                "department": site.department,
                "major": site.major,
                "url": site.url,
                "source_sheet": site.source_sheet,
            }
            for site in sites[:80]
        ],
    }
