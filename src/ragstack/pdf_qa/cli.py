"""Command-line interface for the PDF Q&A system."""

import json
import sys
from pathlib import Path
from typing import Optional

import click

from .graph import create_qa_graph


@click.group()
def cli():
    """PDF Q&A System CLI - Query PDFs with citations."""
    pass


@cli.command()
@click.argument("query", type=str)
@click.option(
    "--pdf",
    type=click.Path(exists=True),
    help="Path to a single PDF file",
)
@click.option(
    "--dir",
    type=click.Path(exists=True),
    help="Path to directory containing PDF files",
)
@click.option(
    "--db",
    type=click.Path(),
    default="pdf_qa.db",
    help="Path to SQLite database (default: pdf_qa.db)",
)
@click.option(
    "--k",
    type=int,
    default=5,
    help="Number of chunks to retrieve (default: 5)",
)
@click.option(
    "--reasoning/--no-reasoning",
    default=False,
    help="Include extended thinking reasoning",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON",
)
def ask(
    query: str,
    pdf: Optional[str],
    dir: Optional[str],
    db: str,
    k: int,
    reasoning: bool,
    output_json: bool,
):
    """Ask a question about PDF(s).

    Examples:
        # Query a single PDF
        pdf-qa ask "What is the main conclusion?" --pdf paper.pdf

        # Query a directory of PDFs
        pdf-qa ask "Compare findings" --dir ./research/

        # With extended thinking
        pdf-qa ask "Explain the methodology" --pdf paper.pdf --reasoning
    """
    if not pdf and not dir:
        click.echo("Error: Provide either --pdf or --dir", err=True)
        sys.exit(1)

    if pdf and dir:
        click.echo("Error: Provide either --pdf or --dir, not both", err=True)
        sys.exit(1)

    click.echo(f"Querying PDF(s)...", err=True)

    graph = create_qa_graph(db_path=db)

    try:
        result = graph.process_query(
            query=query,
            pdf_path=pdf,
            pdf_dir=dir,
            retrieve_k=k,
            include_reasoning=reasoning,
        )

        if result.get("error"):
            click.echo(f"Error: {result['error']}", err=True)
            sys.exit(1)

        if output_json:
            response = result.get("response")
            output = {
                "query": response.question if response else query,
                "answer": response.answer if response else None,
                "sources": [
                    {
                        "page": r.chunk.start_page,
                        "page_end": r.chunk.end_page,
                        "score": r.final_score,
                        "text": r.chunk.text[:100],
                    }
                    for r in (response.sources if response else [])
                ],
                "reasoning": response.reasoning if response and response.reasoning else None,
            }
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo("\n" + "=" * 70)
            click.echo(result.get("formatted_response"))
            click.echo("=" * 70)

    finally:
        graph.close()


@cli.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option(
    "--db",
    type=click.Path(),
    default="pdf_qa.db",
    help="Path to SQLite database",
)
def index(pdf_path: str, db: str):
    """Index a PDF for querying.

    Pre-indexing is optional—documents are indexed on first query.
    This command is useful for batch indexing or validation.
    """
    click.echo(f"Indexing {pdf_path}...", err=True)

    graph = create_qa_graph(db_path=db)

    try:
        result = graph.process_query(
            query="dummy",  # Not used for indexing
            pdf_path=pdf_path,
            retrieve_k=0,  # Skip retrieval
        )

        if result.get("error"):
            click.echo(f"Error: {result['error']}", err=True)
            sys.exit(1)

        indexed = result.get("indexed_count", 0)
        click.echo(f"✓ Indexed {indexed} chunks from {Path(pdf_path).name}")

    finally:
        graph.close()


@cli.command()
@click.option(
    "--db",
    type=click.Path(),
    default="pdf_qa.db",
    help="Path to SQLite database",
)
def interactive(db: str):
    """Start interactive Q&A session.

    Query your PDFs in a loop. Type 'quit' or 'exit' to end.
    """
    click.echo("PDF Q&A System (Interactive Mode)")
    click.echo("=" * 50)
    click.echo("Enter PDF path or directory to index (optional):")

    pdf_input = click.prompt("PDF path [skip]", default="", show_default=False)

    graph = create_qa_graph(db_path=db)

    try:
        if pdf_input:
            click.echo(f"Indexing {pdf_input}...", err=True)
            graph.process_query("dummy", pdf_path=pdf_input if Path(pdf_input).is_file() else None,
                              pdf_dir=pdf_input if Path(pdf_input).is_dir() else None)

        click.echo("\nReady for queries. Type 'quit' to exit.\n")

        while True:
            query = click.prompt("Query")

            if query.lower() in ("quit", "exit"):
                break

            result = graph.process_query(
                query=query,
                pdf_path=pdf_input if pdf_input and Path(pdf_input).is_file() else None,
                pdf_dir=pdf_input if pdf_input and Path(pdf_input).is_dir() else None,
            )

            if result.get("error"):
                click.echo(f"Error: {result['error']}\n")
            else:
                click.echo("\n" + result.get("formatted_response", "No response") + "\n")

    finally:
        graph.close()
        click.echo("Goodbye!")


@cli.command()
@click.option(
    "--db",
    type=click.Path(),
    default="pdf_qa.db",
    help="Path to SQLite database",
)
def info(db: str):
    """Show information about indexed documents."""
    from .vector_store import SQLiteVecStore

    store = SQLiteVecStore(db_path=db)

    try:
        cursor = store.connection.cursor()

        # Count documents
        cursor.execute("SELECT COUNT(DISTINCT document_id) FROM chunks")
        doc_count = cursor.fetchone()[0]

        # Count chunks
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        # Count embeddings
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        embedding_count = cursor.fetchone()[0]

        click.echo("Database Info")
        click.echo("=" * 50)
        click.echo(f"Location: {db}")
        click.echo(f"Documents: {doc_count}")
        click.echo(f"Chunks: {chunk_count}")
        click.echo(f"Embeddings: {embedding_count}")

        if doc_count > 0:
            click.echo("\nDocuments:")
            cursor.execute(
                "SELECT DISTINCT document_id, COUNT(*) as chunk_count "
                "FROM chunks GROUP BY document_id"
            )
            for doc_id, count in cursor.fetchall():
                click.echo(f"  {doc_id}: {count} chunks")

    finally:
        store.close()


if __name__ == "__main__":
    cli()
