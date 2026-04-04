from __future__ import annotations

import argparse
import json
import os
import sys

from app.agents.specialists import ExplanationAgent, parse_answer_payload
from app.indexer.pipeline import IndexingPipeline
from app.llm.gemini import GeminiClient
from app.models import RetrievedChunk
from app.retrieval.hybrid import HybridRetriever
from app.settings import get_settings
from app.storage.mongo_store import MongoStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roleready")
    sub = parser.add_subparsers(dest="command", required=True)

    index = sub.add_parser("index")
    index_sub = index.add_subparsers(dest="index_command", required=True)

    full = index_sub.add_parser("full")
    full.add_argument("--repo-path", required=True)
    full.add_argument("--repo-id", required=True)
    full.add_argument("--branch", default="main")

    incr = index_sub.add_parser("incremental")
    incr.add_argument("--repo-path", required=True)
    incr.add_argument("--repo-id", required=True)
    incr.add_argument("--branch", default="main")

    ensure = index_sub.add_parser("ensure-indexes")
    ensure.add_argument("--repo-id", required=True)

    retrieve = sub.add_parser("retrieve")
    retrieve_sub = retrieve.add_subparsers(dest="retrieve_command", required=True)
    query = retrieve_sub.add_parser("query")
    query.add_argument("--repo-id", required=True)
    query.add_argument("--branch", default="main")
    query.add_argument("--q", required=True)
    query.add_argument("--top-k", type=int, default=8)
    query.add_argument("--lang")
    query.add_argument("--path-prefix")

    jobs = sub.add_parser("jobs")
    jobs_sub = jobs.add_subparsers(dest="jobs_command", required=True)
    jobs_status = jobs_sub.add_parser("status")
    jobs_status.add_argument("--repo-id", required=True)

    debug = sub.add_parser("debug")
    debug_sub = debug.add_subparsers(dest="debug_command", required=True)
    debug_dim = debug_sub.add_parser("validate-dimensions")
    debug_dim.add_argument("--expected", type=int)

    t = sub.add_parser("tui")
    t.add_argument("--repo-id", required=True)
    t.add_argument("--branch", default="main")
    t.add_argument("--top-k", type=int, default=5)

    return parser


def _to_retrieved_chunks(chunks: list[dict]) -> list[RetrievedChunk]:
    out: list[RetrievedChunk] = []
    for c in chunks:
        out.append(
            RetrievedChunk(
                chunk_id=c.get("chunk_id", ""),
                file_path=c.get("file_path", ""),
                start_line=int(c.get("start_line", 1)),
                end_line=int(c.get("end_line", 1)),
                text=c.get("content", ""),
                score=float(c.get("score", 0.0)),
                symbol_name=c.get("symbol_name"),
            )
        )
    return out


def _print_tui_help() -> None:
    print(
        """
Commands:
  /help                         Show this help
  /mode retrieve                Retrieval-only mode (raw chunks)
  /mode backend|frontend|security|architect|debugger
                                Run selected expert agent over retrieved chunks
  /topk <n>                     Set top-k for retrieval
  /lang <language>              Set language filter (python/typescript/...)
  /path <prefix>                Set file path prefix filter
  /clearfilters                 Clear language/path filters
  /status                       Show current TUI state
  exit                          Quit
""".strip()
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    store = MongoStore(settings.mongodb_uri, settings.mongodb_db)
    pipeline = IndexingPipeline(settings, store)
    retriever = HybridRetriever(settings, store)

    try:
        if args.command == "index" and args.index_command == "full":
            pipeline.ensure_indexes(args.repo_id)
            out = pipeline.index_full(args.repo_path, args.repo_id, args.branch)
            print(json.dumps(out, indent=2, default=str))
            return 0

        if args.command == "index" and args.index_command == "incremental":
            pipeline.ensure_indexes(args.repo_id)
            out = pipeline.index_incremental(args.repo_path, args.repo_id, args.branch)
            print(json.dumps(out, indent=2, default=str))
            return 0

        if args.command == "index" and args.index_command == "ensure-indexes":
            pipeline.ensure_indexes(args.repo_id)
            print(json.dumps({"ok": True, "repo_id": args.repo_id}, indent=2))
            return 0

        if args.command == "retrieve" and args.retrieve_command == "query":
            out = retriever.query(
                repo_id=args.repo_id,
                branch=args.branch,
                q=args.q,
                top_k=args.top_k,
                lang=args.lang,
                path_prefix=args.path_prefix,
                include_graph=True,
            )
            print(json.dumps(out, indent=2, default=str))
            return 0

        if args.command == "jobs" and args.jobs_command == "status":
            jobs = list(
                store.index_jobs.find({"repo_id": args.repo_id}, {"_id": 0})
                .sort("started_at", -1)
                .limit(20)
            )
            print(
                json.dumps(
                    {"repo_id": args.repo_id, "jobs": jobs}, indent=2, default=str
                )
            )
            return 0

        if args.command == "debug" and args.debug_command == "validate-dimensions":
            expected = args.expected if args.expected else settings.embedding_dim
            store.validate_embedding_dimension(expected)
            print(json.dumps({"ok": True, "expected_dim": expected}, indent=2))
            return 0

        if args.command == "tui":
            mode = "retrieve"
            user_role = "backend"
            top_k = args.top_k
            lang: str | None = None
            path_prefix: str | None = None

            print("Hackbite TUI (type 'exit' to quit)")
            print(
                json.dumps(
                    {
                        "repo_id": args.repo_id,
                        "branch": args.branch,
                        "top_k": top_k,
                        "embedding_provider": settings.embedding_provider,
                        "embedding_model": settings.embedding_model,
                        "embedding_dim": settings.embedding_dim,
                    },
                    indent=2,
                )
            )
            _print_tui_help()

            while True:
                try:
                    q = input("\nask> ").strip()
                except EOFError:
                    break

                if not q:
                    continue
                if q.lower() in {"exit", "quit"}:
                    break

                if q.startswith("/"):
                    parts = q.split(maxsplit=1)
                    cmd = parts[0].lower()
                    arg = parts[1].strip() if len(parts) > 1 else ""

                    if cmd == "/help":
                        _print_tui_help()
                        continue
                    if cmd == "/mode":
                        allowed = {
                            "retrieve",
                            "backend",
                            "frontend",
                            "security",
                            "architect",
                            "debugger",
                        }
                        if arg not in allowed:
                            print(
                                json.dumps(
                                    {
                                        "error": "invalid mode",
                                        "allowed": sorted(allowed),
                                    },
                                    indent=2,
                                )
                            )
                            continue
                        mode = arg
                        if mode != "retrieve":
                            user_role = mode
                        print(json.dumps({"ok": True, "mode": mode}, indent=2))
                        continue
                    if cmd == "/topk":
                        try:
                            top_k = max(1, int(arg))
                            print(json.dumps({"ok": True, "top_k": top_k}, indent=2))
                        except Exception:
                            print(
                                json.dumps({"error": "topk must be integer"}, indent=2)
                            )
                        continue
                    if cmd == "/lang":
                        lang = arg or None
                        print(json.dumps({"ok": True, "lang": lang}, indent=2))
                        continue
                    if cmd == "/path":
                        path_prefix = arg or None
                        print(
                            json.dumps(
                                {"ok": True, "path_prefix": path_prefix}, indent=2
                            )
                        )
                        continue
                    if cmd == "/clearfilters":
                        lang = None
                        path_prefix = None
                        print(
                            json.dumps(
                                {"ok": True, "lang": None, "path_prefix": None},
                                indent=2,
                            )
                        )
                        continue
                    if cmd == "/status":
                        print(
                            json.dumps(
                                {
                                    "mode": mode,
                                    "user_role": user_role,
                                    "top_k": top_k,
                                    "lang": lang,
                                    "path_prefix": path_prefix,
                                },
                                indent=2,
                            )
                        )
                        continue

                    print(json.dumps({"error": f"unknown command: {cmd}"}, indent=2))
                    continue

                out = retriever.query(
                    repo_id=args.repo_id,
                    branch=args.branch,
                    q=q,
                    top_k=top_k,
                    lang=lang,
                    path_prefix=path_prefix,
                    include_graph=True,
                )

                if mode == "retrieve":
                    print(json.dumps(out, indent=2, default=str))
                    continue

                try:
                    api_key = os.getenv("GEMINI_API_KEY", "")
                    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
                    llm = GeminiClient(api_key=api_key, model=model)
                    explainer = ExplanationAgent(llm)

                    rc = _to_retrieved_chunks(out.get("chunks", []))
                    raw = explainer.explain(
                        query=q, user_role=user_role, chunks=rc, history=""
                    )
                    answer, confidence, citations = parse_answer_payload(raw, rc)

                    print(
                        json.dumps(
                            {
                                "mode": mode,
                                "answer": answer,
                                "confidence": confidence,
                                "citations": [c.model_dump() for c in citations],
                                "retrieval": {
                                    "confidence": out.get("confidence", 0.0),
                                    "chunks": out.get("chunks", []),
                                },
                            },
                            indent=2,
                            default=str,
                        )
                    )
                except Exception as exc:
                    print(
                        json.dumps(
                            {
                                "mode": mode,
                                "error": str(exc),
                                "hint": "For expert mode set GEMINI_API_KEY (optional GEMINI_MODEL), or use /mode retrieve.",
                                "retrieval": out,
                            },
                            indent=2,
                            default=str,
                        )
                    )
            return 0

        print("Unsupported command")
        return 2
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
