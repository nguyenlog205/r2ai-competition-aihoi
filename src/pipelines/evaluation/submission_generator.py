#!/usr/bin/env python3
"""
Generate submission file (results.json) for the competition.
Usage: python -m src.pipelines.evaluation.submission_generator --test-questions data/test_questions.json --output results.json
"""

import json
import argparse
from typing import List, Dict, Any
from tqdm import tqdm

from src.utils.config_loader import get_config
from src.utils.log import get_logger
from src.pipelines.retrieval.utils.retriever import LegalRetriever
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

logger = get_logger("submission_generator")


class AnswerGenerator:
    """Local LLM for answer generation using Gemma 2 9B (compliant with competition rules)."""

    def __init__(self, model_name: str = "google/gemma-2-9b-it"):
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        )
        logger.info(f"Loaded LLM: {model_name}")

    def generate(self, question: str, contexts: List[str]) -> str:
        """
        Generate an answer based on the retrieved context chunks.
        """
        if not contexts:
            return "Không tìm thấy thông tin liên quan trong cơ sở dữ liệu."

        # Build prompt
        context_text = "\n\n".join([f"[Đoạn {i+1}]: {ctx}" for i, ctx in enumerate(contexts)])
        prompt = f"""Bạn là trợ lý pháp lý chuyên nghiệp. Dựa vào các đoạn văn bản dưới đây, hãy trả lời câu hỏi một cách chính xác, ngắn gọn và chỉ sử dụng thông tin có trong các đoạn văn bản.

Các đoạn văn bản:
{context_text}

Câu hỏi: {question}

Trả lời:"""

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=4096).to(self.model.device)
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.7,
            do_sample=True,
            top_p=0.95,
        )
        answer = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # Remove the prompt part (everything after "Trả lời:")
        if "Trả lời:" in answer:
            answer = answer.split("Trả lời:")[-1].strip()
        return answer


def format_doc_meta(doc_title: str, doc_number: str, doc_type: str = "Luật") -> str:
    """
    Format document metadata for relevant_docs and relevant_articles fields.
    Expected format: "<doc_number>|<doc_type> <doc_number> <short_title>"
    Example: "04/2017/QH14|Luật 04/2017/QH14 Luật Hỗ trợ doanh nghiệp nhỏ và vừa"
    The short_title is usually the document's title without the law number.
    """
    # Try to extract a clean title without the number
    import re
    # Remove law number from title (e.g., "Luật Doanh nghiệp số 59/2020/QH14" -> "Luật Doanh nghiệp")
    title_clean = re.sub(r'\s+số\s+\S+', '', doc_title).strip()
    short_title = f"{doc_type} {doc_number} {title_clean}"
    return f"{doc_number}|{short_title}"


def extract_articles_from_chunks(chunks: List[Dict[str, Any]]) -> List[str]:
    """
    Extract unique (doc_number, doc_title, article_number) from chunks.
    Format: "<doc_number>|<formatted_title>|<Điều X>"
    """
    articles = set()
    for ch in chunks:
        doc_number = ch.get("document_number") or ch.get("number") or ""
        doc_title = ch.get("document_title") or ""
        article = ch.get("article_number")
        if doc_number and article:
            formatted_title = format_doc_meta(doc_title, doc_number).split("|")[1]  # just the title part
            articles.add(f"{doc_number}|{formatted_title}|Điều {article}")
    return list(articles)


def extract_docs_from_chunks(chunks: List[Dict[str, Any]]) -> List[str]:
    """
    Extract unique (doc_number, doc_title) from chunks.
    Format: "<doc_number>|<formatted_title>"
    """
    docs = set()
    for ch in chunks:
        doc_number = ch.get("document_number") or ch.get("number") or ""
        doc_title = ch.get("document_title") or ""
        if doc_number:
            docs.add(format_doc_meta(doc_title, doc_number))
    return list(docs)


def main():
    parser = argparse.ArgumentParser(description="Generate competition submission file.")
    parser.add_argument("--test-questions", required=True, help="Path to test questions JSON file.")
    parser.add_argument("--output", default="results.json", help="Output JSON file name.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve per question.")
    parser.add_argument("--retrieve-k", type=int, default=100, help="Number of candidates before rerank.")
    parser.add_argument("--rerank", action="store_true", default=True, help="Use reranking.")
    parser.add_argument("--no-rerank", dest="rerank", action="store_false", help="Disable reranking.")
    parser.add_argument("--use-llm", action="store_true", default=True, help="Generate answer with LLM.")
    parser.add_argument("--no-llm", dest="use_llm", action="store_false", help="Skip LLM (use concatenated context as answer).")
    args = parser.parse_args()

    # Load test questions
    with open(args.test_questions, "r", encoding="utf-8") as f:
        test_questions = json.load(f)
    logger.info(f"Loaded {len(test_questions)} test questions.")

    # Initialize retriever
    retriever = LegalRetriever(rerank=args.rerank)

    # Initialize LLM if needed
    llm = None
    if args.use_llm:
        try:
            llm = AnswerGenerator()
        except Exception as e:
            logger.error(f"Failed to load LLM: {e}. Falling back to context concatenation.")
            llm = None

    results = []
    for q in tqdm(test_questions, desc="Processing questions"):
        qid = q["id"]
        question = q["question"]

        # Retrieve relevant chunks
        if args.rerank:
            chunks = retriever.search_with_rerank(question, top_k=args.top_k, retrieve_k=args.retrieve_k)
        else:
            chunks = retriever.vector_search(question, top_k=args.top_k)

        # Extract documents and articles
        relevant_docs = extract_docs_from_chunks(chunks)
        relevant_articles = extract_articles_from_chunks(chunks)

        # Generate answer
        if chunks:
            contexts = [ch["content"] for ch in chunks]
            if llm:
                answer = llm.generate(question, contexts)
            else:
                # Fallback: concatenate top chunk content
                answer = contexts[0]
        else:
            answer = "Không tìm thấy thông tin liên quan."

        results.append({
            "id": qid,
            "question": question,
            "answer": answer,
            "relevant_docs": relevant_docs,
            "relevant_articles": relevant_articles,
        })

    # Write results
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved results to {args.output}")

    retriever.close()


if __name__ == "__main__":
    main()