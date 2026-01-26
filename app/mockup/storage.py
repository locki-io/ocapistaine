# app/mockup/storage.py
"""
Redis Storage for Mockup Validation Results

Stores contribution analysis results in Redis for:
- Historical tracking by date
- Opik dataset export for prompt optimization
- Batch result persistence

Key format: contribution_mockup:forseti461:charter:{date}:{contribution_id}
"""

import json
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

from app.data.redis_client import redis_connection, get_redis_connection
from app.services import AgentLogger

_logger = AgentLogger("mockup_storage")


# Redis key patterns for mockup storage
class MockupKeys:
    """Redis key patterns for mockup validation storage."""

    # Main storage: contribution_mockup:forseti461:charter:{date}:{id}
    VALIDATION = "contribution_mockup:forseti461:charter:{date}:{id}"

    # Index of all validations for a date
    DATE_INDEX = "contribution_mockup:forseti461:charter:index:{date}"

    # Latest validation results (for quick access)
    LATEST = "contribution_mockup:forseti461:charter:latest"

    # Dataset export metadata
    DATASET_META = "contribution_mockup:forseti461:dataset:{dataset_name}"

    @staticmethod
    def validation(contribution_id: str, date_str: Optional[str] = None) -> str:
        """Get key for a validation result."""
        if date_str is None:
            date_str = date.today().isoformat()
        return f"contribution_mockup:forseti461:charter:{date_str}:{contribution_id}"

    @staticmethod
    def date_index(date_str: Optional[str] = None) -> str:
        """Get key for date index."""
        if date_str is None:
            date_str = date.today().isoformat()
        return f"contribution_mockup:forseti461:charter:index:{date_str}"

    @staticmethod
    def dataset_meta(dataset_name: str) -> str:
        """Get key for dataset metadata."""
        return f"contribution_mockup:forseti461:dataset:{dataset_name}"


# TTL constants
class MockupTTL:
    """Time-to-live for mockup data."""

    VALIDATION = 604800 * 4  # 28 days
    LATEST = 86400  # 24 hours
    DATASET_META = 604800  # 7 days


@dataclass
class ValidationRecord:
    """
    Complete validation record for storage and Opik dataset export.

    Designed to match Opik optimizer dataset format:
    - input: fields used by the prompt (title, body, category)
    - expected_output: validation results for training
    - metadata: additional context for analysis
    """

    # Contribution identification
    id: str
    date: str

    # Input fields (for Opik prompt optimization)
    title: str
    body: str
    category: Optional[str] = None
    constat_factuel: str = ""
    idees_ameliorations: str = ""

    # Expected output (for Opik evaluation)
    is_valid: bool = True
    violations: List[str] = field(default_factory=list)
    encouraged_aspects: List[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""

    # Category classification result
    suggested_category: Optional[str] = None
    category_confidence: float = 0.0
    category_reasoning: str = ""

    # Mockup metadata
    source: str = "mock"  # framaforms, mock, derived, input
    expected_valid: Optional[bool] = None  # Ground truth if known
    parent_id: Optional[str] = None
    similarity_to_parent: Optional[float] = None
    distance_from_parent: Optional[int] = None
    violations_injected: List[str] = field(default_factory=list)

    # Execution metadata
    provider: str = ""
    model: str = ""
    execution_time_ms: Optional[int] = None
    trace_id: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationRecord":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_opik_item(self) -> Dict[str, Any]:
        """
        Convert to Opik dataset item format.

        Structure for prompt optimization:
        {
            "input": { ... prompt variables ... },
            "expected_output": { ... expected response ... },
            "metadata": { ... additional info ... }
        }
        """
        return {
            "input": {
                "title": self.title,
                "body": self.body,
                "category": self.category,
                "constat_factuel": self.constat_factuel,
                "idees_ameliorations": self.idees_ameliorations,
            },
            "expected_output": {
                "is_valid": self.is_valid,
                "violations": self.violations,
                "encouraged_aspects": self.encouraged_aspects,
                "confidence": self.confidence,
                "reasoning": self.reasoning,
                "category": self.suggested_category or self.category,
            },
            "metadata": {
                "id": self.id,
                "date": self.date,
                "source": self.source,
                "expected_valid": self.expected_valid,
                "parent_id": self.parent_id,
                "similarity_to_parent": self.similarity_to_parent,
                "violations_injected": self.violations_injected,
                "provider": self.provider,
                "model": self.model,
                "trace_id": self.trace_id,
            },
        }

    def matches_expected(self) -> Optional[bool]:
        """Check if validation matches expected result (if known)."""
        if self.expected_valid is None:
            return None
        return self.is_valid == self.expected_valid


class MockupStorage:
    """
    Redis storage manager for mockup validation results.

    Provides:
    - Store/retrieve individual validation records
    - Date-based indexing for historical analysis
    - Export to Opik dataset format
    - Batch operations for efficiency
    """

    def __init__(self):
        """Initialize storage manager."""
        self._logger = AgentLogger("mockup_storage")

    def save_validation(self, record: ValidationRecord) -> bool:
        """
        Save a validation record to Redis.

        Args:
            record: ValidationRecord to save

        Returns:
            True if successful
        """
        try:
            with redis_connection() as r:
                # Main storage
                key = MockupKeys.validation(record.id, record.date)
                r.setex(key, MockupTTL.VALIDATION, json.dumps(record.to_dict()))

                # Add to date index (sorted set by timestamp)
                index_key = MockupKeys.date_index(record.date)
                r.zadd(index_key, {record.id: datetime.fromisoformat(record.timestamp).timestamp()})
                r.expire(index_key, MockupTTL.VALIDATION)

                # Update latest
                r.hset(MockupKeys.LATEST, record.id, json.dumps(record.to_dict()))
                r.expire(MockupKeys.LATEST, MockupTTL.LATEST)

            self._logger.info(
                "SAVE_VALIDATION",
                id=record.id[:8],
                date=record.date,
                is_valid=record.is_valid,
            )
            return True

        except Exception as e:
            self._logger.error("SAVE_VALIDATION_ERROR", error=str(e))
            return False

    def get_validation(
        self, contribution_id: str, date_str: Optional[str] = None
    ) -> Optional[ValidationRecord]:
        """
        Get a validation record by ID.

        Args:
            contribution_id: Contribution ID
            date_str: Optional date string (defaults to today)

        Returns:
            ValidationRecord if found, None otherwise
        """
        try:
            with redis_connection() as r:
                key = MockupKeys.validation(contribution_id, date_str)
                data = r.get(key)
                if data:
                    return ValidationRecord.from_dict(json.loads(data))
                return None
        except Exception as e:
            self._logger.error("GET_VALIDATION_ERROR", error=str(e))
            return None

    def get_validations_by_date(self, date_str: Optional[str] = None) -> List[ValidationRecord]:
        """
        Get all validations for a specific date.

        Args:
            date_str: Date string (defaults to today)

        Returns:
            List of ValidationRecords
        """
        if date_str is None:
            date_str = date.today().isoformat()

        records = []
        try:
            with redis_connection() as r:
                # Get all IDs from index
                index_key = MockupKeys.date_index(date_str)
                ids = r.zrange(index_key, 0, -1)

                # Fetch each record
                for contrib_id in ids:
                    key = MockupKeys.validation(contrib_id, date_str)
                    data = r.get(key)
                    if data:
                        records.append(ValidationRecord.from_dict(json.loads(data)))

            self._logger.info("GET_BY_DATE", date=date_str, count=len(records))
            return records

        except Exception as e:
            self._logger.error("GET_BY_DATE_ERROR", error=str(e))
            return records

    def get_latest_validations(self, limit: int = 100) -> List[ValidationRecord]:
        """
        Get the most recent validations.

        Args:
            limit: Maximum number to return

        Returns:
            List of ValidationRecords
        """
        records = []
        try:
            with redis_connection() as r:
                all_data = r.hgetall(MockupKeys.LATEST)
                for data in list(all_data.values())[:limit]:
                    records.append(ValidationRecord.from_dict(json.loads(data)))

            return sorted(records, key=lambda r: r.timestamp, reverse=True)

        except Exception as e:
            self._logger.error("GET_LATEST_ERROR", error=str(e))
            return records

    def save_batch(self, records: List[ValidationRecord]) -> int:
        """
        Save multiple validation records efficiently.

        Args:
            records: List of ValidationRecords

        Returns:
            Number of records saved
        """
        saved = 0
        try:
            with redis_connection() as r:
                pipe = r.pipeline()

                for record in records:
                    # Main storage
                    key = MockupKeys.validation(record.id, record.date)
                    pipe.setex(key, MockupTTL.VALIDATION, json.dumps(record.to_dict()))

                    # Date index
                    index_key = MockupKeys.date_index(record.date)
                    pipe.zadd(index_key, {record.id: datetime.fromisoformat(record.timestamp).timestamp()})

                    # Latest
                    pipe.hset(MockupKeys.LATEST, record.id, json.dumps(record.to_dict()))

                pipe.execute()
                saved = len(records)

            self._logger.info("SAVE_BATCH", count=saved)
            return saved

        except Exception as e:
            self._logger.error("SAVE_BATCH_ERROR", error=str(e))
            return saved

    def export_to_opik_format(
        self,
        date_str: Optional[str] = None,
        source_filter: Optional[List[str]] = None,
        valid_only: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Export validations to Opik dataset format.

        Args:
            date_str: Date to export (None for all latest)
            source_filter: Filter by source types
            valid_only: Filter by validity

        Returns:
            List of Opik dataset items
        """
        if date_str:
            records = self.get_validations_by_date(date_str)
        else:
            records = self.get_latest_validations(limit=1000)

        # Apply filters
        if source_filter:
            records = [r for r in records if r.source in source_filter]
        if valid_only is not None:
            records = [r for r in records if r.is_valid == valid_only]

        items = [r.to_opik_item() for r in records]

        self._logger.info(
            "EXPORT_OPIK",
            count=len(items),
            date=date_str,
            filters={"source": source_filter, "valid_only": valid_only},
        )

        return items

    def get_statistics(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics for validations.

        Args:
            date_str: Date to get stats for (None for latest)

        Returns:
            Statistics dictionary
        """
        if date_str:
            records = self.get_validations_by_date(date_str)
        else:
            records = self.get_latest_validations()

        if not records:
            return {"count": 0}

        valid_count = sum(1 for r in records if r.is_valid)
        with_expected = [r for r in records if r.expected_valid is not None]
        matches = sum(1 for r in with_expected if r.matches_expected())

        sources = {}
        for r in records:
            sources[r.source] = sources.get(r.source, 0) + 1

        return {
            "count": len(records),
            "valid_count": valid_count,
            "invalid_count": len(records) - valid_count,
            "valid_ratio": valid_count / len(records) if records else 0,
            "with_expected": len(with_expected),
            "matches_expected": matches,
            "accuracy": matches / len(with_expected) if with_expected else None,
            "sources": sources,
            "avg_confidence": sum(r.confidence for r in records) / len(records),
        }

    def clear_date(self, date_str: str) -> int:
        """
        Clear all validations for a specific date.

        Args:
            date_str: Date to clear

        Returns:
            Number of records deleted
        """
        deleted = 0
        try:
            with redis_connection() as r:
                # Get all IDs from index
                index_key = MockupKeys.date_index(date_str)
                ids = r.zrange(index_key, 0, -1)

                # Delete each record
                pipe = r.pipeline()
                for contrib_id in ids:
                    key = MockupKeys.validation(contrib_id, date_str)
                    pipe.delete(key)
                    pipe.hdel(MockupKeys.LATEST, contrib_id)

                # Delete index
                pipe.delete(index_key)
                pipe.execute()

                deleted = len(ids)
                self._logger.info("CLEAR_DATE", date=date_str, deleted=deleted)

        except Exception as e:
            self._logger.error("CLEAR_DATE_ERROR", error=str(e))

        return deleted


# Global storage instance
_storage: Optional[MockupStorage] = None


def get_storage() -> MockupStorage:
    """Get or create global storage instance."""
    global _storage
    if _storage is None:
        _storage = MockupStorage()
    return _storage
