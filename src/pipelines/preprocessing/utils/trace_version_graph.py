#!/usr/bin/env python3
"""
Trace the amendment version graph with a beautiful visual output.
Given a chunk ID, find all related chunks (both directions) and display them
as a tree, including document metadata, article/clause/point numbers, and content previews.
"""

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Set, List, Dict, Any, Optional, Tuple
import argparse

# ANSI color codes (if terminal supports)
COLORS = {
    'reset': '\033[0m',
    'bold': '\033[1m',
    'red': '\033[91m',
    'green': '\033[92m',
    'yellow': '\033[93m',
    'blue': '\033[94m',
    'magenta': '\033[95m',
    'cyan': '\033[96m',
    'gray': '\033[90m',
}

def colorize(text: str, color: str, use_color: bool = True) -> str:
    if use_color:
        return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"
    return text

def load_relations(relations_file: str) -> Tuple[defaultdict, defaultdict]:
    """Load amendment relations and build forward and reverse maps."""
    with open(relations_file, "r", encoding="utf-8") as f:
        relations = json.load(f)
    forward = defaultdict(list)
    reverse = defaultdict(list)
    for rel in relations:
        src = rel.get("source_chunk_id")
        tgt = rel.get("target_chunk_id")
        if src and tgt:
            forward[src].append(tgt)
            reverse[tgt].append(src)
    return forward, reverse

def load_chunk_index(chunk_index_file: str) -> Dict[str, Any]:
    """Load chunk_index.json."""
    with open(chunk_index_file, "r", encoding="utf-8") as f:
        return json.load(f)

def load_document_index(doc_index_file: str) -> Dict[str, Any]:
    """Load document_index.json."""
    with open(doc_index_file, "r", encoding="utf-8") as f:
        return json.load(f)

def get_related_chunk_ids(start_id: str, forward: dict, reverse: dict, max_depth: Optional[int] = None) -> Set[str]:
    """BFS to collect all chunk IDs reachable via forward or reverse links."""
    visited = set()
    queue = deque([start_id])
    depth = {start_id: 0}
    while queue:
        cur = queue.popleft()
        if cur in visited:
            continue
        visited.add(cur)
        cur_depth = depth[cur]
        if max_depth is not None and cur_depth >= max_depth:
            continue
        for nxt in forward.get(cur, []):
            if nxt not in visited:
                depth[nxt] = cur_depth + 1
                queue.append(nxt)
        for nxt in reverse.get(cur, []):
            if nxt not in visited:
                depth[nxt] = cur_depth + 1
                queue.append(nxt)
    return visited

def get_document_info(doc_id: str, doc_index: Dict[str, Any]) -> Dict[str, str]:
    """Return a short document info string."""
    meta = doc_index.get(doc_id, {})
    return {
        "title": meta.get("title", "Unknown document"),
        "number": meta.get("number", ""),
        "url": meta.get("url", ""),
    }

def format_location(chunk: Dict[str, Any]) -> str:
    """Format the hierarchical location of a chunk."""
    parts = []
    if chunk.get("article_number"):
        parts.append(f"Điều {chunk['article_number']}")
    if chunk.get("clause_number"):
        parts.append(f"Khoản {chunk['clause_number']}")
    if chunk.get("point"):
        parts.append(f"Điểm {chunk['point']}")
    if not parts:
        return "Toàn bộ văn bản"
    return " / ".join(parts)

def print_chunk_info(chunk_id: str, chunk_index: Dict[str, Any], doc_index: Dict[str, Any],
                     level: int = 0, use_color: bool = True, prefix: str = ""):
    """Pretty print a chunk with document metadata and content preview."""
    if chunk_id not in chunk_index:
        print(f"{prefix}{colorize('⚠️  Chunk not found:', 'red', use_color)} {chunk_id}")
        return

    ch = chunk_index[chunk_id]
    doc_id = ch.get("doc_id")
    doc_info = get_document_info(doc_id, doc_index) if doc_id else {"title": "Unknown", "number": ""}

    # Build location string
    location = format_location(ch)

    # Determine color based on level (source/target)
    color = 'green' if level == 0 else 'cyan' if level % 2 == 1 else 'yellow'

    # Pretty print
    indent = "  " * level
    print(f"{indent}{prefix}{colorize('┌─ Chunk:', color, use_color)} {colorize(chunk_id, 'bold', use_color)}")
    print(f"{indent}│  📄 {colorize(doc_info['title'], 'blue', use_color)} {doc_info['number']}")
    print(f"{indent}│  📍 {location}")
    if ch.get("level"):
        print(f"{indent}│  🏷️  Level: {ch['level']}")
    if ch.get("amendment_type"):
        print(f"{indent}│  ✏️  Amendment: {ch['amendment_type']}")
    # Content preview
    content = ch.get("chunk_content", "")
    preview = content[:200].replace('\n', ' ').strip()
    if preview:
        print(f"{indent}│  📝 Preview: {preview}{'…' if len(content) > 200 else ''}")
    print(f"{indent}└─")

def build_tree_from_bfs(start_id: str, forward: dict, reverse: dict,
                        chunk_index: dict, doc_index: dict,
                        use_color: bool = True, max_depth: int = 3) -> None:
    """
    Build a hierarchical tree representation.
    We'll do BFS but also capture parent-child relationships.
    Since it's a graph, we need to avoid infinite loops; we'll use visited set.
    """
    visited = set()
    queue = deque()
    # We'll store (chunk_id, parent_id, depth)
    queue.append((start_id, None, 0))
    # To avoid duplicates, we still track visited after printing
    printed = set()
    while queue:
        cur_id, parent_id, depth = queue.popleft()
        if cur_id in printed:
            continue
        printed.add(cur_id)
        # Print with appropriate indentation
        prefix = ""
        if parent_id is not None:
            # simple indentation: depth spaces
            pass
        print_chunk_info(cur_id, chunk_index, doc_index, level=depth, use_color=use_color, prefix="")
        # Add children (forward and reverse) but mark them as next level
        # To create a tree, we need to decide direction: treat forward as "amends" and reverse as "amended by"
        # We can show both as separate branches.
        # Here we'll just show all related as next level, but to avoid duplication we add them if not printed.
        for nxt in forward.get(cur_id, []):
            if nxt not in printed and depth < max_depth:
                queue.append((nxt, cur_id, depth+1))
        for nxt in reverse.get(cur_id, []):
            if nxt not in printed and depth < max_depth:
                queue.append((nxt, cur_id, depth+1))

def get_linear_chain(start_id: str, forward: dict, reverse: dict, direction: str = 'forward') -> List[str]:
    """Get a linear chain in one direction (for simple chains)."""
    chain = []
    cur = start_id
    visited = set()
    while cur and cur not in visited:
        visited.add(cur)
        chain.append(cur)
        if direction == 'forward':
            nxt = forward.get(cur, [])
        else:
            nxt = reverse.get(cur, [])
        if not nxt:
            break
        # If multiple, take the first (simple heuristic)
        cur = nxt[0]
    return chain

def main():
    parser = argparse.ArgumentParser(description="Trace amendment version graph with beautiful output.")
    parser.add_argument("chunk_id", help="Starting chunk ID (e.g., from chunk_index.json).")
    parser.add_argument("--relations", default="data/index/amendment_relations.json",
                        help="Path to amendment_relations.json")
    parser.add_argument("--chunk-index", default="data/index/chunk_index.json",
                        help="Path to chunk_index.json")
    parser.add_argument("--doc-index", default="data/index/document_index.json",
                        help="Path to document_index.json")
    parser.add_argument("--max-depth", type=int, default=3,
                        help="Maximum depth for tree output (default: 3).")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")
    parser.add_argument("--linear", action="store_true", help="Show linear chain only (if no branching).")
    args = parser.parse_args()

    use_color = not args.no_color

    # Load data
    forward, reverse = load_relations(args.relations)
    chunk_index = load_chunk_index(args.chunk_index)
    doc_index = load_document_index(args.doc_index)

    print(colorize("\n" + "="*80, 'bold', use_color))
    print(colorize(f"📜 VERSION GRAPH TRACER", 'bold', use_color))
    print(colorize(f"Starting chunk: {args.chunk_id}", 'yellow', use_color))
    print(colorize("="*80 + "\n", 'bold', use_color))

    if args.linear:
        # Show linear chains if the start node has single child and single parent
        fwd_count = len(forward.get(args.chunk_id, []))
        rev_count = len(reverse.get(args.chunk_id, []))
        if fwd_count == 1 or rev_count == 1:
            if fwd_count == 1:
                print(colorize("➡️  Forward chain (amending towards final version):", 'green', use_color))
                chain = get_linear_chain(args.chunk_id, forward, reverse, 'forward')
                for i, cid in enumerate(chain):
                    print_chunk_info(cid, chunk_index, doc_index, level=i, use_color=use_color)
            if rev_count == 1:
                print(colorize("\n⬅️  Backward chain (original source to this chunk):", 'cyan', use_color))
                chain = get_linear_chain(args.chunk_id, forward, reverse, 'backward')
                for i, cid in enumerate(chain):
                    print_chunk_info(cid, chunk_index, doc_index, level=i, use_color=use_color)
        else:
            print(colorize("⚠️  Branching detected; cannot display a single linear chain. Use tree view instead.", 'yellow', use_color))
    else:
        # Build tree view (BFS based on depth)
        print(colorize("🌳 Amendment graph (tree view, up to depth {}):".format(args.max_depth), 'bold', use_color))
        print(colorize("   Green = starting node, Cyan = child, Yellow = parent", 'gray', use_color))
        print("")
        build_tree_from_bfs(args.chunk_id, forward, reverse, chunk_index, doc_index, use_color, args.max_depth)

    print(colorize("\n" + "="*80 + "\n", 'bold', use_color))

if __name__ == "__main__":
    main()