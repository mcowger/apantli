"""Catwalk pricing service for model cost calculation."""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional
import asyncio
import os

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ModelPricing:
    """Pricing data for a model."""

    cost_per_1m_in: float
    cost_per_1m_out: float


class CatwalkPricingService:
    """Manages model pricing data from catwalk API."""

    DEFAULT_CATWALK_URL = "https://catwalk.charm.sh/v2/providers"
    REFRESH_INTERVAL = 6 * 60 * 60  # 6 hours in seconds

    def __init__(self, catwalk_url: Optional[str] = None) -> None:
        """Initialize the pricing service.

        Args:
            catwalk_url: Optional URL override for testing. Falls back to
                         CATWALK_URL env var, then to DEFAULT_CATWALK_URL.
        """
        self._catwalk_url = (
            catwalk_url
            or os.environ.get("CATWALK_URL")
            or self.DEFAULT_CATWALK_URL
        )
        # provider_catwalk_name → model_id → pricing
        self._pricing_index: Dict[str, Dict[str, ModelPricing]] = {}
        self._last_refresh: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Fetch initial pricing data on startup."""
        await self._fetch_and_build_index()

    async def _fetch_and_build_index(self) -> None:
        """Fetch catwalk data and build the pricing index.

        On network failure, logs an error and keeps the existing index
        (or starts with an empty index on first failure).
        """
        async with self._lock:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(self._catwalk_url, timeout=30.0)
                    response.raise_for_status()
                    providers = response.json()

                # Build new index
                new_index: Dict[str, Dict[str, ModelPricing]] = {}
                for provider in providers:
                    provider_id = provider.get("id")
                    if not provider_id:
                        continue

                    models_dict: Dict[str, ModelPricing] = {}
                    for model in provider.get("models", []):
                        model_id = model.get("id")
                        cost_in = model.get("cost_per_1m_in")
                        cost_out = model.get("cost_per_1m_out")

                        if model_id and cost_in is not None and cost_out is not None:
                            models_dict[model_id] = ModelPricing(
                                cost_per_1m_in=float(cost_in),
                                cost_per_1m_out=float(cost_out),
                            )

                    if models_dict:
                        new_index[provider_id] = models_dict

                self._pricing_index = new_index
                self._last_refresh = datetime.utcnow()

                total_models = sum(len(models) for models in new_index.values())
                logger.info(
                    "pricing_index_updated",
                    providers=len(new_index),
                    models=total_models,
                )

            except httpx.HTTPError as e:
                logger.error(
                    "catwalk_fetch_failed",
                    error=str(e),
                    url=self._catwalk_url,
                    has_existing_index=bool(self._pricing_index),
                )
            except (ValueError, TypeError, KeyError) as e:
                logger.error(
                    "catwalk_parse_failed",
                    error=str(e),
                    url=self._catwalk_url,
                )

    def calculate_cost(
        self,
        catwalk_name: Optional[str],
        costing_model: Optional[str],
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate cost for a completion.

        Args:
            catwalk_name: The provider's catwalk identifier (e.g., "openai", "anthropic")
            costing_model: The model ID for costing lookup
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens

        Returns:
            The calculated cost in dollars.
            Returns 0.0 with a warning log if model or provider not found.
        """
        if not catwalk_name:
            logger.warning(
                "pricing_lookup_failed",
                reason="missing_catwalk_name",
                costing_model=costing_model,
            )
            return 0.0

        if not costing_model:
            logger.warning(
                "pricing_lookup_failed",
                reason="missing_costing_model",
                catwalk_name=catwalk_name,
            )
            return 0.0

        provider_models = self._pricing_index.get(catwalk_name)
        if provider_models is None:
            logger.warning(
                "pricing_lookup_failed",
                reason="provider_not_found",
                catwalk_name=catwalk_name,
                costing_model=costing_model,
            )
            return 0.0

        pricing = provider_models.get(costing_model)
        if pricing is None:
            logger.warning(
                "pricing_lookup_failed",
                reason="model_not_found",
                catwalk_name=catwalk_name,
                costing_model=costing_model,
                available_models=list(provider_models.keys())[:10],  # Limit for log size
            )
            return 0.0

        cost = (prompt_tokens * pricing.cost_per_1m_in / 1_000_000) + (
            completion_tokens * pricing.cost_per_1m_out / 1_000_000
        )

        logger.debug(
            "cost_calculated",
            catwalk_name=catwalk_name,
            costing_model=costing_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
        )

        return cost

    async def refresh_loop(self) -> None:
        """Background loop that refreshes pricing data every 6 hours.

        This method runs indefinitely and should be started as a background task.
        On refresh failure, it logs the error and retries on the next interval.
        """
        while True:
            await asyncio.sleep(self.REFRESH_INTERVAL)
            logger.info("pricing_refresh_starting")
            await self._fetch_and_build_index()
