"""One-shot builder for frozen rag_qa_v1 — run then keep questions.json immutable."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent

P_SURVEY = "paper-2312.10997v5"
P_STACK = "paper-2601.05264v1"
P_BLEND = "paper-2404.07220v2"
REPO = "repo-langchain-ai-langchain"
URL_BLEND = "https://arxiv.org/abs/2404.07220v2"
URL_SURVEY = "https://arxiv.org/abs/2312.10997v5"
URL_STACK = "https://arxiv.org/abs/2601.05264v1"
URL_REPO = "https://github.com/langchain-ai/langchain"


def q(
    qid,
    question,
    qtype,
    gold_ids,
    expected_sources,
    facts,
    notes="",
    needs_mcp=False,
    should_refuse=False,
    difficulty="easy",
):
    return {
        "question_id": qid,
        "question": question,
        "eval_type": qtype,
        "gold_evidence_ids": gold_ids,
        "expected_sources": expected_sources,
        "reference_points": facts,
        "needs_mcp": needs_mcp,
        "should_refuse": should_refuse,
        "difficulty": difficulty,
        "notes": notes,
    }


def main() -> None:
    items = []
    direct = [
        (
            "What are the three generations of RAG paradigms described in the survey?",
            [P_SURVEY],
            [URL_SURVEY],
            ["Naive RAG", "Advanced RAG", "Modular RAG"],
        ),
        (
            "What challenges of LLMs does the RAG survey say RAG helps address?",
            [P_SURVEY],
            [URL_SURVEY],
            ["hallucination", "outdated knowledge"],
        ),
        (
            "What methodology does paper 2312.10997 use?",
            [P_SURVEY],
            [URL_SURVEY],
            ["systematic literature review", "survey"],
        ),
        (
            "What limitation of RAG systems is mentioned regarding multi-hop reasoning?",
            [P_SURVEY],
            [URL_SURVEY],
            ["multi-hop reasoning"],
        ),
        (
            "What is the research problem addressed by Engineering the RAG Stack?",
            [P_STACK],
            [URL_STACK],
            ["fragmented", "taxonomy"],
        ),
        (
            "What years does the RAG Stack review cover?",
            [P_STACK],
            [URL_STACK],
            ["2018", "2025"],
        ),
        (
            "Why are trust and alignment frameworks important for RAG?",
            [P_STACK],
            [URL_STACK],
            ["trust", "production"],
        ),
        (
            "What does Blended RAG blend for retrieval?",
            [P_BLEND],
            [URL_BLEND],
            ["dense", "sparse"],
        ),
        (
            "On which datasets was Blended RAG evaluated?",
            [P_BLEND],
            [URL_BLEND],
            ["NQ", "TREC-COVID", "SQUAD"],
        ),
        (
            "What metrics does Blended RAG report?",
            [P_BLEND],
            [URL_BLEND],
            ["F1", "Exact Match"],
        ),
        (
            "What is the primary bottleneck for RAG accuracy according to Blended RAG?",
            [P_BLEND],
            [URL_BLEND],
            ["retriever"],
        ),
        (
            "Does Blended RAG claim hybrid query strategies outperform pure semantic search?",
            [P_BLEND],
            [URL_BLEND],
            ["hybrid", "outperform"],
        ),
        ("What is LangChain described as?", [REPO], [URL_REPO], ["agent", "framework"]),
        (
            "Which LangChain module covers agent orchestration?",
            [REPO],
            [URL_REPO],
            ["langgraph"],
        ),
        (
            "How can LangChain be installed according to the evidence?",
            [REPO],
            [URL_REPO],
            ["uv add langchain", "pip"],
        ),
        (
            "Name vector stores supported by LangChain evidence.",
            [REPO],
            [URL_REPO],
            ["Chroma", "Pinecone"],
        ),
        (
            "What limitation of LangChain is noted?",
            [REPO],
            [URL_REPO],
            ["abstraction overhead"],
        ),
        (
            "What arXiv identifier belongs to Blended RAG?",
            [P_BLEND],
            [URL_BLEND],
            ["2404.07220"],
        ),
        ("Who are authors of Blended RAG?", [P_BLEND], [URL_BLEND], ["Sawarkar"]),
        (
            "What evidence_id corresponds to the LangChain repository?",
            [REPO],
            [URL_REPO],
            ["repo-langchain-ai-langchain"],
        ),
    ]
    for i, (question, gids, srcs, facts) in enumerate(direct, 1):
        items.append(q(f"q{i:02d}", question, "direct", gids, srcs, facts))

    cross = [
        (
            "Compare Naive RAG from the survey with Blended RAG hybrid retrieval.",
            [P_SURVEY, P_BLEND],
            [URL_SURVEY, URL_BLEND],
            ["Naive RAG", "dense", "sparse"],
        ),
        (
            "How do Modular RAG and LangChain modular components relate?",
            [P_SURVEY, REPO],
            [URL_SURVEY, URL_REPO],
            ["Modular", "langgraph"],
        ),
        (
            "Which paper emphasizes taxonomy while another emphasizes blended retrieval?",
            [P_STACK, P_BLEND],
            [URL_STACK, URL_BLEND],
            ["taxonomy", "blended"],
        ),
        (
            "Link retrieval quality bottleneck claims across Blended RAG and the survey.",
            [P_BLEND, P_SURVEY],
            [URL_BLEND, URL_SURVEY],
            ["retriever", "bottleneck"],
        ),
        (
            "How can LangChain implement ideas from Blended RAG?",
            [P_BLEND, REPO],
            [URL_BLEND, URL_REPO],
            ["retriever", "vector"],
        ),
        (
            "What evaluation themes appear in both the survey and Blended RAG?",
            [P_SURVEY, P_BLEND],
            [URL_SURVEY, URL_BLEND],
            ["accuracy", "faithfulness"],
        ),
        (
            "Relate trust frameworks in the stack review to LangChain observability.",
            [P_STACK, REPO],
            [URL_STACK, URL_REPO],
            ["trust", "LangSmith"],
        ),
        (
            "Summarize how Advanced RAG enhancements differ from Blended hybrid indexes.",
            [P_SURVEY, P_BLEND],
            [URL_SURVEY, URL_BLEND],
            ["Advanced", "hybrid"],
        ),
    ]
    for i, (question, gids, srcs, facts) in enumerate(cross, 21):
        items.append(
            q(f"q{i:02d}", question, "cross_doc", gids, srcs, facts, difficulty="medium")
        )

    disc = [
        (
            "Which paper specifically studies Blended dense+sparse retrieval rather than a broad survey?",
            [P_BLEND],
            [URL_BLEND],
            ["Blended RAG"],
            "discriminate",
        ),
        (
            "Which paper is a comprehensive survey of RAG paradigms including Naive/Advanced/Modular?",
            [P_SURVEY],
            [URL_SURVEY],
            ["survey", "Modular RAG"],
            "discriminate",
        ),
        (
            "Which paper focuses on engineering taxonomy and trust frameworks for RAG stacks?",
            [P_STACK],
            [URL_STACK],
            ["taxonomy", "trust"],
            "discriminate",
        ),
        (
            "Return the source_url for Blended RAG, not the survey.",
            [P_BLEND],
            [URL_BLEND],
            ["2404.07220"],
            "source_trace",
        ),
        (
            "Which evidence discusses LangGraph rather than arXiv surveys?",
            [REPO],
            [URL_REPO],
            ["langgraph"],
            "discriminate",
        ),
        (
            "Identify the 2024 Blended RAG arXiv paper among RAG-related evidence.",
            [P_BLEND],
            [URL_BLEND],
            ["2024", "2404"],
            "discriminate",
        ),
    ]
    for i, (question, gids, srcs, facts, et) in enumerate(disc, 29):
        items.append(q(f"q{i:02d}", question, et, gids, srcs, facts, difficulty="medium"))

    mcp = [
        ("Find recent papers on quantum error correction surface codes 2024.", ["quantum"]),
        ("Search arXiv for diffusion model classifier-free guidance surveys.", ["diffusion"]),
        ("Get an overview of huggingface/transformers repository structure.", ["transformers"]),
        ("What are latest papers on toolformer-style LLM tool use?", ["toolformer"]),
        ("Retrieve papers about graph neural networks for drug discovery 2023.", ["GNN"]),
        ("Find GitHub repos implementing Mixture-of-Experts routing.", ["MoE"]),
        ("Search academic papers on federated learning differential privacy.", ["federated"]),
        ("Look up papers comparing ColBERT late interaction retrieval.", ["ColBERT"]),
    ]
    for i, (question, facts) in enumerate(mcp, 35):
        items.append(
            q(
                f"q{i:02d}",
                question,
                "needs_mcp",
                [],
                [],
                facts,
                needs_mcp=True,
                difficulty="hard",
                notes="out_of_corpus",
            )
        )

    refuse = [
        "What is the exact GPU hours used to train GPT-5 according to our artifacts?",
        "Quote the private API key stored in the LangChain evidence.",
        "Did Blended RAG win the 2026 Best Paper award at ACL?",
        "What is Yunfan Gao's personal phone number?",
        "Provide unpublished experimental scores for Modular RAG on secret datasets.",
    ]
    for i, question in enumerate(refuse, 43):
        items.append(
            q(
                f"q{i:02d}",
                question,
                "should_refuse",
                [],
                [],
                [],
                should_refuse=True,
                difficulty="hard",
            )
        )

    cite = [
        (
            "Cite the Blended RAG paper with its evidence_id and arXiv URL.",
            [P_BLEND],
            [URL_BLEND],
            ["paper-2404.07220v2", "arxiv.org"],
        ),
        (
            "Cite the LangChain repository evidence_id and github URL.",
            [REPO],
            [URL_REPO],
            ["repo-langchain-ai-langchain", "github.com"],
        ),
        (
            "Provide source_url for the RAG survey paper 2312.10997.",
            [P_SURVEY],
            [URL_SURVEY],
            ["2312.10997"],
        ),
    ]
    for i, (question, gids, srcs, facts) in enumerate(cite, 48):
        items.append(q(f"q{i:02d}", question, "citation", gids, srcs, facts))

    assert len(items) == 50, len(items)
    payload = {
        "version": "rag_qa_v1",
        "created": "2026-10-17",
        "corpus": "docs/scholar-flow/samples/rag-test-001",
        "description": "Fixed 50-question ScholarFlow RAG eval set. Do not edit after baseline freeze.",
        "count": 50,
        "questions": items,
    }
    (OUT / "questions.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "VERSION").write_text("rag_qa_v1\n", encoding="utf-8")
    print("wrote", OUT / "questions.json", "n=", len(items))


if __name__ == "__main__":
    main()
