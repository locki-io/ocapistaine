# app/mockup/dataset.py
"""
Opik Dataset Management for Forseti Prompt Optimization

Creates and manages datasets for use with Opik's prompt optimization studio.

Dataset structure for charter validation optimization:
- Input: title, body, category (contribution fields)
- Expected output: is_valid, violations, encouraged_aspects (validation results)
- Metadata: source, similarity metrics, injected violations

Usage:
    manager = DatasetManager()
    manager.create_charter_dataset("forseti-charter-v1")
    manager.add_from_redis(date_str="2026-01-26")
    manager.sync_to_opik()
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any

from app.agents.tracing.opik import get_tracer
from app.mockup.storage import get_storage, ValidationRecord
from app.services import AgentLogger

_logger = AgentLogger("mockup_dataset")


# Dataset naming conventions
DATASET_PREFIX = "forseti-charter"
DATASET_TRAINING = f"{DATASET_PREFIX}-training"
DATASET_VALIDATION = f"{DATASET_PREFIX}-validation"
DATASET_TEST = f"{DATASET_PREFIX}-test"


class DatasetManager:
    """
    Manages Opik datasets for Forseti prompt optimization.

    Provides:
    - Dataset creation with proper structure
    - Import from Redis validation storage
    - Export for optimization studio
    - Train/validation/test split management
    """

    def __init__(self):
        """Initialize dataset manager."""
        self._tracer = get_tracer()
        self._storage = get_storage()
        self._datasets: Dict[str, List[Dict[str, Any]]] = {}
        self._logger = AgentLogger("dataset_manager")

    @property
    def opik_enabled(self) -> bool:
        """Check if Opik is enabled."""
        return self._tracer.enabled

    def create_charter_dataset(
        self,
        name: str,
        description: Optional[str] = None,
    ) -> bool:
        """
        Create a new dataset for charter validation optimization.

        Args:
            name: Dataset name (e.g., "forseti-charter-training")
            description: Dataset description

        Returns:
            True if created successfully
        """
        if not self.opik_enabled:
            self._logger.warning("CREATE_DATASET_SKIPPED", reason="opik_disabled")
            # Still track locally
            self._datasets[name] = []
            return True

        default_desc = (
            f"Charter validation dataset for Forseti 461 prompt optimization. "
            f"Created: {datetime.now().isoformat()}"
        )

        dataset = self._tracer.create_dataset(
            name=name,
            description=description or default_desc,
        )

        if dataset:
            self._datasets[name] = []
            self._logger.info("CREATE_DATASET", name=name)
            return True

        self._logger.error("CREATE_DATASET_FAILED", name=name)
        return False

    def add_items(
        self,
        dataset_name: str,
        items: List[Dict[str, Any]],
    ) -> int:
        """
        Add items to a dataset.

        Args:
            dataset_name: Target dataset name
            items: List of Opik dataset items

        Returns:
            Number of items added
        """
        if dataset_name not in self._datasets:
            self._datasets[dataset_name] = []

        # Track locally
        self._datasets[dataset_name].extend(items)

        # Sync to Opik if enabled
        if self.opik_enabled:
            success = self._tracer.add_to_dataset(dataset_name, items)
            if not success:
                self._logger.warning("ADD_ITEMS_OPIK_FAILED", name=dataset_name)

        self._logger.info("ADD_ITEMS", name=dataset_name, count=len(items))
        return len(items)

    def add_from_redis(
        self,
        dataset_name: str,
        date_str: Optional[str] = None,
        source_filter: Optional[List[str]] = None,
        valid_only: Optional[bool] = None,
    ) -> int:
        """
        Add items from Redis storage to dataset.

        Args:
            dataset_name: Target dataset name
            date_str: Date to import from (None for latest)
            source_filter: Filter by source types
            valid_only: Filter by validity

        Returns:
            Number of items added
        """
        items = self._storage.export_to_opik_format(
            date_str=date_str,
            source_filter=source_filter,
            valid_only=valid_only,
        )

        if not items:
            self._logger.info("ADD_FROM_REDIS_EMPTY", date=date_str)
            return 0

        return self.add_items(dataset_name, items)

    def add_validation_record(
        self,
        dataset_name: str,
        record: ValidationRecord,
    ) -> bool:
        """
        Add a single validation record to dataset.

        Args:
            dataset_name: Target dataset name
            record: ValidationRecord to add

        Returns:
            True if successful
        """
        item = record.to_opik_item()
        added = self.add_items(dataset_name, [item])
        return added > 0

    def create_train_val_test_split(
        self,
        source_date: Optional[str] = None,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
    ) -> Dict[str, int]:
        """
        Create training, validation, and test datasets from Redis data.

        Args:
            source_date: Date to import from (None for latest)
            train_ratio: Ratio for training set
            val_ratio: Ratio for validation set
            test_ratio: Ratio for test set

        Returns:
            Dict with counts for each split
        """
        # Get all items
        items = self._storage.export_to_opik_format(date_str=source_date)

        if not items:
            return {"training": 0, "validation": 0, "test": 0}

        # Calculate split indices
        n = len(items)
        train_end = int(n * train_ratio)
        val_end = train_end + int(n * val_ratio)

        # Create datasets
        self.create_charter_dataset(DATASET_TRAINING, "Training set for Forseti charter optimization")
        self.create_charter_dataset(DATASET_VALIDATION, "Validation set for Forseti charter optimization")
        self.create_charter_dataset(DATASET_TEST, "Test set for Forseti charter optimization")

        # Split items (shuffle would be better, but keeping order for reproducibility)
        train_items = items[:train_end]
        val_items = items[train_end:val_end]
        test_items = items[val_end:]

        # Add to datasets
        train_count = self.add_items(DATASET_TRAINING, train_items)
        val_count = self.add_items(DATASET_VALIDATION, val_items)
        test_count = self.add_items(DATASET_TEST, test_items)

        self._logger.info(
            "CREATE_SPLIT",
            total=n,
            training=train_count,
            validation=val_count,
            test=test_count,
        )

        return {
            "training": train_count,
            "validation": val_count,
            "test": test_count,
        }

    def get_local_dataset(self, name: str) -> List[Dict[str, Any]]:
        """
        Get locally tracked dataset items.

        Args:
            name: Dataset name

        Returns:
            List of dataset items
        """
        return self._datasets.get(name, [])

    def get_dataset_stats(self, name: str) -> Dict[str, Any]:
        """
        Get statistics for a dataset.

        Args:
            name: Dataset name

        Returns:
            Statistics dictionary
        """
        items = self.get_local_dataset(name)

        if not items:
            return {"count": 0}

        valid_count = sum(1 for i in items if i.get("expected_output", {}).get("is_valid"))
        sources = {}
        for item in items:
            src = item.get("metadata", {}).get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1

        return {
            "count": len(items),
            "valid_count": valid_count,
            "invalid_count": len(items) - valid_count,
            "sources": sources,
            "opik_synced": self.opik_enabled,
        }

    def export_for_optimizer(
        self,
        dataset_name: str,
        format: str = "list",
    ) -> Any:
        """
        Export dataset in format ready for Opik optimizer.

        Args:
            dataset_name: Dataset to export
            format: Export format ("list" or "dict")

        Returns:
            Dataset in specified format
        """
        items = self.get_local_dataset(dataset_name)

        if format == "dict":
            return {
                "name": dataset_name,
                "items": items,
                "count": len(items),
                "created": datetime.now().isoformat(),
            }

        return items

    def sync_to_opik(self, dataset_name: Optional[str] = None) -> Dict[str, int]:
        """
        Sync local datasets to Opik.

        Args:
            dataset_name: Specific dataset to sync (None for all)

        Returns:
            Dict of synced counts per dataset
        """
        if not self.opik_enabled:
            self._logger.warning("SYNC_SKIPPED", reason="opik_disabled")
            return {}

        datasets_to_sync = [dataset_name] if dataset_name else list(self._datasets.keys())
        synced = {}

        for name in datasets_to_sync:
            items = self._datasets.get(name, [])
            if items:
                success = self._tracer.add_to_dataset(name, items)
                if success:
                    synced[name] = len(items)
                    self._logger.info("SYNC_DATASET", name=name, count=len(items))
                else:
                    self._logger.error("SYNC_FAILED", name=name)

        return synced


# Global manager instance
_manager: Optional[DatasetManager] = None


def get_dataset_manager() -> DatasetManager:
    """Get or create global dataset manager."""
    global _manager
    if _manager is None:
        _manager = DatasetManager()
    return _manager


def create_optimization_dataset(
    name: str = "forseti-charter-optimization",
    from_date: Optional[str] = None,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to create a dataset for prompt optimization.

    Args:
        name: Dataset name
        from_date: Date to import validations from
        description: Dataset description

    Returns:
        Dataset info with statistics
    """
    manager = get_dataset_manager()

    # Create dataset
    manager.create_charter_dataset(name, description)

    # Import from Redis
    count = manager.add_from_redis(
        dataset_name=name,
        date_str=from_date,
    )

    # Get stats
    stats = manager.get_dataset_stats(name)

    return {
        "name": name,
        "imported": count,
        "opik_enabled": manager.opik_enabled,
        **stats,
    }
