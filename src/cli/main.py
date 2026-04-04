import typer
import json
from src.indexer.pipeline import IndexingPipeline
from src.storage.repositories import DBRepository
from src.retrieval.search import Retriever
from src.core.config import settings

app = typer.Typer(help="Hackbite 2 Codebase Vectorization CLI")
index_app = typer.Typer(help="Indexing commands")
retrieve_app = typer.Typer(help="Retrieval commands")
jobs_app = typer.Typer(help="Jobs status commands")
debug_app = typer.Typer(help="Debug and utility commands")

app.add_typer(index_app, name="index")
app.add_typer(retrieve_app, name="retrieve")
app.add_typer(jobs_app, name="jobs")
app.add_typer(debug_app, name="debug")

@index_app.command("full")
def index_full(
    repo_path: str = typer.Option(..., help="Local path to repository"),
    repo_id: str = typer.Option(..., help="Unique ID for this repo in DB"),
    branch: str = typer.Option("main", help="Branch name")
):
    """Run full indexing on a repository."""
    pipeline = IndexingPipeline(repo_path, repo_id, branch)
    job = pipeline.run(mode="full")
    if job.status == "failed":
        typer.secho("Indexing Failed", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    typer.secho("Full index complete", fg=typer.colors.GREEN)
    typer.echo(job.model_dump_json(indent=2))

@index_app.command("incremental")
def index_incremental(
    repo_path: str = typer.Option(..., help="Local path to repository"),
    repo_id: str = typer.Option(..., help="Unique ID for this repo in DB"),
    branch: str = typer.Option("main", help="Branch name")
):
    """Run incremental indexing on a repository."""
    pipeline = IndexingPipeline(repo_path, repo_id, branch)
    job = pipeline.run(mode="incremental")
    if job.status == "failed":
        typer.secho("Indexing Failed", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    typer.secho("Incremental index complete", fg=typer.colors.GREEN)
    typer.echo(job.model_dump_json(indent=2))

@index_app.command("ensure-indexes")
def ensure_indexes():
    """Ensure standard strings and vector indexes exist."""
    db = DBRepository()
    db.ensure_indexes()
    typer.secho("Indexes successfully verified/created.", fg=typer.colors.GREEN)

@retrieve_app.command("query")
def retrieve_query(
    q: str = typer.Option(..., help="Search query"),
    repo_id: str = typer.Option(..., help="Target Repo ID"),
    branch: str = typer.Option("main", help="Target Branch"),
    top_k: int = typer.Option(5, help="Top K results to retrieve"),
    lang: str = typer.Option(None, help="Language filter (Not fully implemented)"),
    path_prefix: str = typer.Option(None, help="Path prefix filter (Not fully implemented)")
):
    """Run hybrid search query."""
    retriever = Retriever()
    results = retriever.retrieve_hybrid(repo_id, branch, q, top_k=top_k)
    
    typer.secho(f"\nResults for '{q}':\n", fg=typer.colors.CYAN)
    for i, res in enumerate(results):
        c = res["chunk"]
        typer.echo(f"[{i+1}] {c['file_path']} L{c['start_line']}-L{c['end_line']}")
        typer.echo(f"  Confidence: {res['confidence']}%  | Reason: {res['reason']}")
        typer.echo(f"  Content snippet: {c['content'][:150].strip()}...\n")

@jobs_app.command("status")
def jobs_status(
    repo_id: str = typer.Option(..., help="Target Repo ID"),
    job_id: str = typer.Option(None, help="Specific Job ID")
):
    """Check indexing job status for a repository."""
    db = DBRepository()
    job = db.get_job(repo_id, job_id)
    if not job:
        typer.secho("No job found.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=1)
    typer.echo(job.model_dump_json(indent=2))

@debug_app.command("validate-dimensions")
def validate_dimensions():
    """Validate that the vector DB embedding dimensions match the local model output."""
    from src.embedder.base import get_embedder
    try:
        embedder = get_embedder()
        vec = embedder.embed_texts(["hello world"])[0]
        actual_dim = len(vec)
        expected_dim = settings.embedding_dim
        
        if actual_dim == expected_dim:
            typer.secho(f"OK! Model outputs dim {actual_dim} matching config {expected_dim}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"MISMATCH! Model outputs dim {actual_dim} but config specifies {expected_dim}", fg=typer.colors.RED)
            raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Error validating dimensions: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
