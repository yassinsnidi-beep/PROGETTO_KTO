"""Command line entrypoint for the full ingestion pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import load_settings
from src.db import ensure_indexes, get_database, upsert_documents
from src.embedding_service import EmbeddingService
from src.ingestion.ingest_companies import build_company_documents
from src.ingestion.ingest_industries import build_industry_documents
from src.ingestion.ingest_patents import build_patent_documents

logger = logging.getLogger(__name__)

CATEGORY_EXTENSIONS = {
    "companies": {".xlsx", ".xlsm", ".xls"},
    "industries": {".csv"},
    "patents": {".xlsx", ".xlsm", ".xls"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest companies, NACE industries and patents into MongoDB Atlas.")
    parser.add_argument("--companies", default=None, help="Optional explicit companies file. Defaults to data/input/companies/*.")
    parser.add_argument("--companies-control", default=None, help="Optional explicit companies embedding control file. Defaults to *control* in companies folder.")
    parser.add_argument("--industries", default=None, help="Optional explicit industries file. Defaults to data/input/industries/*.")
    parser.add_argument("--patents", default=None, help="Optional explicit patents file. Defaults to data/input/patents/*.")
    parser.add_argument("--input-root", default="data/input")
    parser.add_argument("--archive-root", default="data/archive")
    parser.add_argument("--error-root", default="data/error")
    parser.add_argument("--skip-companies", action="store_true")
    parser.add_argument("--skip-industries", action="store_true")
    parser.add_argument("--skip-patents", action="store_true")
    parser.add_argument("--generate-embeddings", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-move", action="store_true", help="Process files without moving them to archive/error.")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def _print_sample(collection_name: str, documents: list[dict[str, Any]]) -> None:
    print(f"\n--- {collection_name} sample ---")
    if not documents:
        print("No valid documents")
        return
    print(json.dumps(documents[0], ensure_ascii=False, indent=2))


def _ensure_data_directories(input_root: str, archive_root: str, error_root: str) -> None:
    """Create input/archive/error category directories if missing."""
    for root in (input_root, archive_root, error_root):
        for category in CATEGORY_EXTENSIONS:
            Path(root, category).mkdir(parents=True, exist_ok=True)


def _discover_files(category: str, explicit_path: str | None, input_root: str) -> list[Path]:
    """Return explicit file or all supported files in data/input/<category>."""
    if explicit_path:
        path = Path(explicit_path)
        return [path] if path.exists() else []
    folder = Path(input_root, category)
    extensions = CATEGORY_EXTENSIONS[category]
    files = sorted(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in extensions)
    if category == "companies":
        files = [f for f in files if "control" not in f.name.lower() and "controllo" not in f.name.lower() and "embedding" not in f.name.lower()]
    return files


def _discover_control_file(input_root: str) -> Path | None:
    """Discover a company embedding control file in the input directory."""
    folder = Path(input_root, "companies")
    if not folder.exists():
        return None
    for file in folder.iterdir():
        if file.is_file() and file.suffix.lower() in {".xlsx", ".xlsm", ".xls"}:
            name_lower = file.name.lower()
            if "control" in name_lower or "controllo" in name_lower or "embedding" in name_lower:
                return file
    return None


def _move_processed_file(source: Path, destination_root: str, category: str) -> Path:
    """Move a processed file, avoiding overwrite with a timestamp suffix."""
    destination_dir = Path(destination_root, category)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if destination.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = destination_dir / f"{source.stem}_{timestamp}{source.suffix}"
    return Path(shutil.move(str(source), str(destination)))


def _process_file(
    *,
    category: str,
    path: Path,
    builder: Any,
    collection_name: str,
    embedding_service: EmbeddingService,
    args: argparse.Namespace,
    db: Any,
    settings: Any,
    control_path: str | None = None,
) -> dict[str, int]:
    """Build, validate, optionally upsert, and route one input file."""
    logger.info("Processing %s file: %s", category, path)
    result = {
        "read": 0,
        "valid": 0,
        "upserted": 0,
        "errors": 0,
        "archived": 0,
        "moved_to_error": 0,
    }
    failed = False
    try:
        builder_kwargs = {}
        if category == "companies":
            builder_kwargs["control_path"] = control_path
        documents, stats = builder(str(path), embedding_service, limit=args.limit, **builder_kwargs)
        result["read"] = stats["read"]
        result["valid"] = stats["valid"]
        result["errors"] = stats["errors"]
        failed = stats["errors"] > 0 or stats["valid"] == 0

        if args.dry_run:
            _print_sample(collection_name, documents)
        else:
            result["upserted"] = upsert_documents(collection_name, documents, db=db, settings=settings)
    except Exception:
        failed = True
        result["errors"] += 1
        logger.exception("Failed processing %s file: %s", category, path)

    if args.dry_run or args.no_move:
        return result

    destination_root = args.error_root if failed else args.archive_root
    moved_to = _move_processed_file(path, destination_root, category)
    if failed:
        result["moved_to_error"] = 1
        logger.info("Moved %s to error folder: %s", path, moved_to)
    else:
        result["archived"] = 1
        logger.info("Archived %s to: %s", path, moved_to)
    return result


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = parse_args()
    _ensure_data_directories(args.input_root, args.archive_root, args.error_root)
    settings = load_settings(force_generate_embeddings=True if args.generate_embeddings else None)
    embedding_service = EmbeddingService(settings)
    db = None
    if not args.dry_run:
        db = get_database(settings)
        ensure_indexes(db)
        # Clear existing companies documents if we are running companies ingestion
        if not args.skip_companies:
            logger.info("Clearing existing 'companies' collection from MongoDB...")
            db["companies"].delete_many({})
            logger.info("Collection 'companies' cleared successfully!")

    summary: dict[str, int] = {
        "companies_read": 0,
        "companies_valid": 0,
        "industries_read": 0,
        "industries_valid": 0,
        "patents_read": 0,
        "patents_valid": 0,
        "documents_upserted": 0,
        "errors": 0,
        "files_processed": 0,
        "files_archived": 0,
        "files_moved_to_error": 0,
    }

    if not args.skip_companies:
        files = _discover_files("companies", args.companies, args.input_root)
        if not files:
            logger.warning("No companies files found")
        # Discover embedding control file
        control_path = args.companies_control
        if not control_path:
            control_file = _discover_control_file(args.input_root)
            if control_file:
                control_path = str(control_file)
                
        for path in files:
            result = _process_file(
                category="companies",
                path=path,
                builder=build_company_documents,
                collection_name="companies",
                embedding_service=embedding_service,
                args=args,
                db=db,
                settings=settings,
                control_path=control_path,
            )
            summary["companies_read"] += result["read"]
            summary["companies_valid"] += result["valid"]
            summary["documents_upserted"] += result["upserted"]
            summary["errors"] += result["errors"]
            summary["files_processed"] += 1
            summary["files_archived"] += result["archived"]
            summary["files_moved_to_error"] += result["moved_to_error"]
            
        # Move control file to archive or error if processed and routing is enabled
        if control_path and not args.dry_run and not args.no_move:
            control_file_path = Path(control_path)
            if control_file_path.exists():
                dest_root = args.error_root if summary["errors"] > 0 else args.archive_root
                moved_to = _move_processed_file(control_file_path, dest_root, "companies")
                logger.info("Moved company control file to: %s", moved_to)

    if not args.skip_industries:
        files = _discover_files("industries", args.industries, args.input_root)
        if not files:
            logger.warning("No industries files found")
        for path in files:
            result = _process_file(
                category="industries",
                path=path,
                builder=build_industry_documents,
                collection_name="industries",
                embedding_service=embedding_service,
                args=args,
                db=db,
                settings=settings,
            )
            summary["industries_read"] += result["read"]
            summary["industries_valid"] += result["valid"]
            summary["documents_upserted"] += result["upserted"]
            summary["errors"] += result["errors"]
            summary["files_processed"] += 1
            summary["files_archived"] += result["archived"]
            summary["files_moved_to_error"] += result["moved_to_error"]

    if not args.skip_patents:
        files = _discover_files("patents", args.patents, args.input_root)
        if not files:
            logger.warning("No patents files found")
        for path in files:
            result = _process_file(
                category="patents",
                path=path,
                builder=build_patent_documents,
                collection_name="patents",
                embedding_service=embedding_service,
                args=args,
                db=db,
                settings=settings,
            )
            summary["patents_read"] += result["read"]
            summary["patents_valid"] += result["valid"]
            summary["documents_upserted"] += result["upserted"]
            summary["errors"] += result["errors"]
            summary["files_processed"] += 1
            summary["files_archived"] += result["archived"]
            summary["files_moved_to_error"] += result["moved_to_error"]

    print("\nIngestion summary")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
