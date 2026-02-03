"""
Firecrawl Document Crawling Task

Crawls municipal documents from configured data sources:
- mairie_arretes: Municipal decrees and publications
- mairie_deliberations: Council deliberations
- commission_controle: Control commission documents

Uses Firecrawl API for web scraping with optional OCR.
"""

from app.services.tasks import _task_boilerplate, TaskError, REDIS_SUCCESS_TTL


def task_firecrawl(date_string: str = None) -> dict:
    """
    Crawl municipal documents from configured sources.

    Workflow:
    1. Load crawl configuration (which sources to crawl)
    2. Execute Firecrawl operations per source
    3. Store results in ext_data/ directories
    4. Update crawl status in Redis

    Args:
        date_string: Date in YYYYMMDD format. Defaults to today.

    Returns:
        dict: Result with document counts per source

    Raises:
        TaskError: If critical failure occurs during crawling
    """
    l, lock_key, success_key, result, task_id = _task_boilerplate(
        "task_firecrawl", date_string
    )

    # Early exit if skipped
    if result["status"] == "skipped":
        return result

    try:
        # Initialize counters
        result["documents_crawled"] = 0
        result["sources_processed"] = 0
        result["sources"] = {}

        # TODO: Check Firecrawl API key
        # import os
        # if not os.getenv("FIRECRAWL_API_KEY"):
        #     result["status"] = "skipped"
        #     result["reason"] = "firecrawl_not_configured"
        #     result["warnings"].append("FIRECRAWL_API_KEY not set")
        #     return result

        # TODO: Load crawl configuration
        # from src.config import DATA_SOURCES
        # active_sources = [s for s in DATA_SOURCES if s.enabled]

        # TODO: Execute crawl for each source
        # from src.firecrawl_utils import FirecrawlManager
        # manager = FirecrawlManager()
        #
        # for source in active_sources:
        #     try:
        #         docs = manager.crawl_website(
        #             url=source.url,
        #             max_pages=source.max_pages,
        #             output_dir=source.output_dir,
        #         )
        #         result["sources"][source.name] = {
        #             "documents": len(docs),
        #             "status": "success"
        #         }
        #         result["documents_crawled"] += len(docs)
        #         result["sources_processed"] += 1
        #     except Exception as e:
        #         result["sources"][source.name] = {
        #             "documents": 0,
        #             "status": "failed",
        #             "error": str(e)
        #         }
        #         result["errors"].append(f"{source.name}: {e}")

        # TODO: Update crawl status in Redis
        # from app.data.redis_client import redis_connection, RedisKeys
        # with redis_connection() as r:
        #     for source_name, source_result in result["sources"].items():
        #         r.hset(
        #             RedisKeys.CRAWL_STATUS.format(source=source_name),
        #             mapping={
        #                 "last_crawl": date_string,
        #                 "documents": source_result["documents"],
        #                 "status": source_result["status"],
        #             }
        #         )

        # Mark task as completed
        result["status"] = "success"
        l.set(success_key, "completed", ex=REDIS_SUCCESS_TTL)

        print(f"task_firecrawl completed: {result['documents_crawled']} documents from {result['sources_processed']} sources")
        return result

    except Exception as e:
        result["status"] = "failed"
        result["errors"].append(str(e))
        print(f"task_firecrawl failed: {e}")
        raise TaskError("failed", str(e))

    finally:
        # Always release lock
        l.delete(lock_key)
