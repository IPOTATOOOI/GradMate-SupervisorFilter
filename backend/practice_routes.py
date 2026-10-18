from __future__ import annotations

import os
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel


router = APIRouter(prefix="/api/practice", tags=["practice"])
DEFAULT_ROOT_CATEGORY = "软件开发"
DEFAULT_SUB_CATEGORY = "专项练习"


class PracticeSubmitRequest(BaseModel):
    answers: dict[str, str] = {}
    question_ids: list[str] = []


def _get_graph():
    """Create a read-only Neo4j client lazily; no graph mutation is supported."""
    try:
        from py2neo import Graph
    except ImportError as error:
        raise HTTPException(status_code=503, detail="题库依赖未安装：请执行 pip install py2neo") from error
    uri = os.getenv("PRACTICE_NEO4J_URI", "").strip()
    user = os.getenv("PRACTICE_NEO4J_USER", "neo4j").strip()
    password = os.getenv("PRACTICE_NEO4J_PASSWORD", "").strip()
    if not uri or not password:
        raise HTTPException(status_code=503, detail="题库 Neo4j 未配置：请在根目录 .env 中填写 PRACTICE_NEO4J_URI、PRACTICE_NEO4J_USER、PRACTICE_NEO4J_PASSWORD。")
    try:
        graph = Graph(uri, auth=(user, password))
        graph.run("RETURN 1 AS ok").data()
        return graph
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"题库 Neo4j 连接失败：{error}") from error


def _parse_choices(value: Any) -> list[dict[str, str]]:
    if isinstance(value, list):
        return [{"label": str(item.get("label") or ""), "text": str(item.get("text") or "")} for item in value if isinstance(item, dict)]
    text = str(value or "")
    matches = re.findall(r"([A-Z])\s*[.、:：]\s*(.*?)(?=(?:[A-Z]\s*[.、:：])|$)", text, flags=re.S)
    return [{"label": label, "text": content.strip()} for label, content in matches]


def _topic_rows(root_category: str, sub_category: str) -> list[dict[str, Any]]:
    graph = _get_graph()
    query = """
    MATCH (r:RootCategory {name: $root_category})-[:HAS_SUB]->(s:SubCategory {name: $sub_category})-[:CONTAINS_TOPIC]->(t:Topic)
    OPTIONAL MATCH (t)-[:INCLUDES]->(q:Question)
    RETURN t.id AS id, t.name AS name, count(q) AS question_count
    ORDER BY t.name ASC
    """
    return graph.run(query, root_category=root_category, sub_category=sub_category).data()


@router.get("/topics")
def read_topics(
    root_category: str = Query(default=DEFAULT_ROOT_CATEGORY),
    sub_category: str = Query(default=DEFAULT_SUB_CATEGORY),
) -> dict[str, Any]:
    rows = _topic_rows(root_category, sub_category)
    topics = [{"id": str(row.get("id") or ""), "name": str(row.get("name") or "未命名主题"), "question_count": int(row.get("question_count") or 0)} for row in rows]
    return {"topics": topics, "root_category": root_category, "sub_category": sub_category, "total": len(topics), "read_only": True}


@router.get("/questions")
def read_questions(topic_id: str = Query(..., min_length=1), limit: int = Query(default=15, ge=1, le=30)) -> dict[str, Any]:
    graph = _get_graph()
    # Read-only query copied from the reference question-bank module and adapted
    # to hide answers until submission.
    query = """
    MATCH (t:Topic {id: $topic_id})-[:INCLUDES]->(q:Question)
    OPTIONAL MATCH (q)-[:MARKED_AS]->(tag:Tag)
    OPTIONAL MATCH (q)-[:TESTS]->(kp:KnowledgePoint)
    WITH q, collect(DISTINCT tag)[0..5] AS tags, collect(DISTINCT kp) AS knowledge_points
    WITH q, tags, knowledge_points ORDER BY rand() LIMIT $limit
    RETURN q.id AS id, q.title AS title, q.content AS content, q.choice AS choice,
           q.type AS type, q.difficulty AS difficulty,
           [tag IN tags | {id: tag.id, name: tag.name}] AS tags,
           [kp IN knowledge_points | {id: kp.id, name: kp.name, level: kp.level}] AS knowledge_points
    """
    rows = graph.run(query, topic_id=topic_id, limit=limit).data()
    questions = [{
        "id": str(row.get("id") or ""), "title": str(row.get("title") or ""),
        "content": str(row.get("content") or ""), "choices": _parse_choices(row.get("choice")),
        "type": str(row.get("type") or "single_choice"), "difficulty": str(row.get("difficulty") or ""),
        "tags": row.get("tags") or [], "knowledge_points": row.get("knowledge_points") or [],
    } for row in rows]
    return {"questions": questions, "count": len(questions), "topic_id": topic_id, "read_only": True}


@router.post("/submit")
def submit_practice(payload: PracticeSubmitRequest) -> dict[str, Any]:
    if not payload.question_ids:
        raise HTTPException(status_code=400, detail="未提供本次练习题目。")
    graph = _get_graph()
    # This query reads answer and explanation only; it does not create or update
    # nodes, relationships, user records, favorites, marks, or weak-point data.
    query = """
    MATCH (q:Question)
    WHERE q.id IN $question_ids
    RETURN q.id AS id, q.type AS type, q.answer AS answer, q.explanation AS explanation
    """
    rows = graph.run(query, question_ids=payload.question_ids).data()
    result_by_id = {str(row.get("id")): row for row in rows}
    results = []
    objective_total = 0
    objective_correct = 0
    for question_id in payload.question_ids:
        row = result_by_id.get(str(question_id))
        if not row:
            continue
        question_type = str(row.get("type") or "single_choice")
        correct_answer = str(row.get("answer") or "").strip()
        if question_type == "essay":
            results.append({"id": str(question_id), "type": "essay", "reference_answer": correct_answer, "explanation": str(row.get("explanation") or "参考答案来自题库。")})
            continue
        objective_total += 1
        correct = str(payload.answers.get(str(question_id), "")).strip() == correct_answer
        objective_correct += int(correct)
        results.append({"id": str(question_id), "type": question_type, "correct": correct, "correct_answer": correct_answer, "explanation": str(row.get("explanation") or "题目解析来自题库。")})
    return {"results": results, "objective_total": objective_total, "objective_correct": objective_correct, "score": round(objective_correct / objective_total * 100) if objective_total else 0, "read_only": True}
