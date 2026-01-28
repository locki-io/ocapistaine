# app/processors/crawl_processor.py
"""
Crawl Processor - Municipal Documents Acquisition Workflow

Orchestrates the crawling of municipal websites using Firecrawl.
Part of the Data Collection Layer (Apache 2.0).

Workflow:
1. Configure sources and crawl parameters
2. Initialize Firecrawl (via FirecrawlManager)
3. Execute crawl/scrape operations
4. Process and store results
5. Log metrics and traces (Opik)
"""

import time
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.logging.domains import ProcessorLogger
from src.firecrawl_utils import FirecrawlManager
from src.config import DataSource, FIRECRAWL_CONFIG, CRAWL_CONFIG, SOURCE_CONFIGS

# Opik integration (optional)
try:
    from opik import track
    OPIK_AVAILABLE = True
except ImportError:
    OPIK_AVAILABLE = False
    track = lambda x: x  # No-op decorator


@dataclass
class CrawlWorkflowConfig:
    """Configuration for crawl processor workflow."""
    mode: str = "scrape"  # "scrape" or "crawl"
    max_pages: int = 100
    dry_run: bool = False
    api_key: Optional[str] = None


@dataclass
class CrawlResult:
    """Result of a crawl workflow run."""
    sources_processed: int = 0
    pages_crawled: int = 0
    successful_sources: List[str] = field(default_factory=list)
    failed_sources: List[str] = field(default_factory=list)
    total_time_ms: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sources_processed": self.sources_processed,
            "pages_crawled": self.pages_crawled,
            "successful_sources": self.successful_sources,
            "failed_sources": self.failed_sources,
            "total_time_ms": self.total_time_ms,
            "errors": self.errors,
            "success_rate": len(self.successful_sources) / self.sources_processed if self.sources_processed > 0 else 0
        }


class CrawlProcessor:
    """
    Processor for municipal document crawling workflow.
    
    Orchestrates:
    - Source configuration loading
    - Firecrawl execution
    - Result storage and logging
    """

    def __init__(self):
        """Initialize the crawl processor."""
        self._logger = ProcessorLogger("crawl")
        self._manager: Optional[FirecrawlManager] = None

    async def check_dependencies(self) -> Dict[str, bool]:
        """Check if dependencies are available."""
        self._logger.log_process_start("crawl", "dependency_check")
        
        status = {
            "firecrawl_key": bool(os.getenv("FIRECRAWL_API_KEY")),
            "opik": OPIK_AVAILABLE,
        }
        
        self._logger.info("DEPENDENCIES", **status)
        return status

    async def run_workflow(
        self,
        sources: List[DataSource],
        config: Optional[CrawlWorkflowConfig] = None,
    ) -> CrawlResult:
        """
        Run the full crawl workflow.

        Args:
            sources: List of data sources to process
            config: Workflow configuration

        Returns:
            CrawlResult with metrics
        """
        config = config or CrawlWorkflowConfig()
        result = CrawlResult()
        start_time = time.time()

        self._logger.log_process_start(
            "crawl",
            "workflow",
            mode=config.mode,
            source_count=len(sources)
        )

        try:
            # Step 1: Initialize Manager (if not dry run)
            if not config.dry_run:
                self._manager = FirecrawlManager(api_key=config.api_key)

            # Step 2: Process Sources
            for source in sources:
                self._logger.info("PROCESS_SOURCE", name=source.name, url=source.url)
                
                if config.dry_run:
                    print(f"🔍 DRY RUN: Would {config.mode} {source.name} ({source.url})")
                    result.successful_sources.append(source.name)
                    continue

                try:
                    success = await self._process_single_source(source, config)
                    if success:
                        result.successful_sources.append(source.name)
                    else:
                        result.failed_sources.append(source.name)
                except Exception as e:
                    self._logger.error("SOURCE_ERROR", name=source.name, error=str(e))
                    result.failed_sources.append(source.name)
                    result.errors.append(f"{source.name}: {str(e)}")

            result.sources_processed = len(sources)

        except Exception as e:
            self._logger.error("WORKFLOW_ERROR", error=str(e))
            result.errors.append(str(e))

        result.total_time_ms = int((time.time() - start_time) * 1000)

        self._logger.log_process_complete(
            "crawl",
            "workflow_result",
            sources=result.sources_processed,
            success=len(result.successful_sources),
            latency_ms=result.total_time_ms
        )

        return result

    @track
    async def _process_single_source(
        self, 
        source: DataSource, 
        config: CrawlWorkflowConfig
    ) -> bool:
        """Process a single data source with tracing."""
        if not self._manager:
            raise RuntimeError("Firecrawl manager not initialized")

        # Get source-specific config
        source_config = SOURCE_CONFIGS.get(source.name, FIRECRAWL_CONFIG)
        
        try:
            if config.mode == "scrape":
                self._manager.scrape_url(
                    url=source.url,
                    output_dir=source.output_dir,
                    **source_config
                )
            else:  # crawl
                crawl_config = {**source_config, **CRAWL_CONFIG}
                self._manager.crawl_website(
                    url=source.url,
                    output_dir=source.output_dir,
                    max_pages=config.max_pages,
                    **crawl_config
                )
            
            return True

        except Exception as e:
            # Error logging handled by caller
            raise e
