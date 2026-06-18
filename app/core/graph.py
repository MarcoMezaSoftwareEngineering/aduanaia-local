"""LangGraph stub.

En Fase 2 el grafo tiene un solo nodo `rag_node`. La forma del `GraphState` ya
incluye los campos que los agentes de Fase 3/4 necesitarán (extracted_data,
risk_level, report, etc.), para evitar reescritura cuando crezca el flujo
descrito en §14 del documento técnico.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, TypedDict
from uuid import UUID

from langgraph.graph import END, START, StateGraph

from app.core import rag


class GraphState(TypedDict, total=False):
    # Entrada
    question: str

    # Recuperación normativa (Fase 2)
    retrieved_sources: list[dict[str, Any]]
    answer: str
    query_id: UUID

    # Campos futuros (Fase 3+) — declarados ahora para forma estable.
    extracted_data: dict[str, Any]
    documentos_faltantes: list[str]
    risk_level: str
    confidence: str
    recommendation: str
    report: str


def _rag_node(state: GraphState) -> GraphState:
    question = state["question"]
    response = rag.answer(question)
    return {
        "question": question,
        "retrieved_sources": [asdict(s) for s in response.sources],
        "answer": response.answer,
        "query_id": response.query_id,
    }


def build_graph():
    g = StateGraph(GraphState)
    g.add_node("rag", _rag_node)
    g.add_edge(START, "rag")
    g.add_edge("rag", END)
    return g.compile()


# Singleton compilado
graph = build_graph()
