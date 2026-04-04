from __future__ import annotations

import argparse
import json
import sys

from app.indexer.pipeline import IndexingPipeline
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

    return parser



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
            jobs = list(store.index_jobs.find({"repo_id": args.repo_id}, {"_id": 0}).sort("started_at", -1).limit(20))
            print(json.dumps({"repo_id": args.repo_id, "jobs": jobs}, indent=2, default=str))
            return 0

        if args.command == "debug" and args.debug_command == "validate-dimensions":
            expected = args.expected if args.expected else settings.embedding_dim
            store.validate_embedding_dimension(expected)
            print(json.dumps({"ok": True, "expected_dim": expected}, indent=2))
            return 0

        print("Unsupported command")
        return 2
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
