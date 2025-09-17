"""
Search service for text-based search functionality across notebook entries.

This module provides comprehensive search capabilities including:
- Full-text search across titles, protocols, and observations
- Tag-based filtering and categorization
- Advanced filtering by cooking method, difficulty, date ranges
- Performance optimization with pagination and caching
- Search result ranking and relevance scoring
"""

import logging
import re
import time
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass

from sqlalchemy import select, and_, or_, func, desc, asc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import NotebookEntry, get_session
from ..utils.config import get_settings
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SearchResult:
    """Structured search result with relevance scoring."""
    entry: NotebookEntry
    relevance_score: float
    snippet: str
    match_fields: List[str]  # Fields that matched the search


@dataclass
class SearchFilter:
    """Search filter parameters."""
    cooking_method: Optional[str] = None
    difficulty_min: Optional[int] = None
    difficulty_max: Optional[int] = None
    servings_min: Optional[int] = None
    servings_max: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    tags: Optional[List[str]] = None
    has_rating: Optional[bool] = None
    has_feedback: Optional[bool] = None


class SearchService:
    """
    Advanced search service for notebook entries.

    Provides comprehensive text-based search with:
    - Multi-field search across content
    - Relevance scoring and ranking
    - Performance optimization
    - Filter composition
    - Result caching
    """

    def __init__(self):
        """Initialize the search service."""
        self.settings = get_settings()
        self._search_cache = {}
        self._cache_ttl = 300  # 5 minutes

    async def search_entries(
        self,
        query: str,
        filters: Optional[SearchFilter] = None,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "relevance",
        sort_order: str = "desc"
    ) -> Tuple[List[SearchResult], int]:
        """
        Perform comprehensive search across notebook entries.

        Args:
            query: Search query string
            filters: Optional search filters
            limit: Maximum number of results
            offset: Offset for pagination
            sort_by: Field to sort by ('relevance', 'date', 'title', 'rating')
            sort_order: Sort order ('asc' or 'desc')

        Returns:
            Tuple of (search results, total count)
        """
        try:
            start_time = time.time()

            # Generate cache key
            cache_key = self._generate_cache_key(query, filters, limit, offset, sort_by, sort_order)

            # Check cache
            if cache_key in self._search_cache:
                cached_item = self._search_cache[cache_key]
                if time.time() - cached_item["timestamp"] < self._cache_ttl:
                    logger.debug(f"Using cached search results for: {query}")
                    return cached_item["results"], cached_item["total_count"]

            # Perform search
            results, total_count = await self._execute_search(
                query, filters, limit, offset, sort_by, sort_order
            )

            # Cache results
            self._search_cache[cache_key] = {
                "results": results,
                "total_count": total_count,
                "timestamp": time.time()
            }

            # Cleanup old cache entries
            self._cleanup_cache()

            search_time = (time.time() - start_time) * 1000
            logger.info(
                f"Search completed: '{query}' -> {len(results)}/{total_count} results in {search_time:.2f}ms"
            )

            return results, total_count

        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return [], 0

    async def _execute_search(
        self,
        query: str,
        filters: Optional[SearchFilter],
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str
    ) -> Tuple[List[SearchResult], int]:
        """Execute the actual search query."""
        try:
            async with get_session() as session:
                # Build base query
                base_query = select(NotebookEntry)
                count_query = select(func.count(NotebookEntry.id))

                # Add search conditions
                search_conditions = []
                if query and query.strip():
                    search_conditions = self._build_search_conditions(query.strip())

                # Add filter conditions
                filter_conditions = []
                if filters:
                    filter_conditions = self._build_filter_conditions(filters)

                # Combine conditions
                all_conditions = []
                if search_conditions:
                    all_conditions.append(or_(*search_conditions))
                if filter_conditions:
                    all_conditions.extend(filter_conditions)

                if all_conditions:
                    condition = and_(*all_conditions)
                    base_query = base_query.where(condition)
                    count_query = count_query.where(condition)

                # Get total count
                total_result = await session.execute(count_query)
                total_count = total_result.scalar() or 0

                # Add sorting
                if sort_by == "relevance" and query.strip():
                    # For relevance sorting, we'll do post-processing
                    base_query = base_query.order_by(desc(NotebookEntry.date))
                else:
                    base_query = self._add_sorting(base_query, sort_by, sort_order)

                # Add pagination
                base_query = base_query.offset(offset).limit(limit)

                # Execute query
                result = await session.execute(base_query)
                entries = result.scalars().all()

                # Convert to search results with relevance scoring
                search_results = []
                for entry in entries:
                    relevance_score = self._calculate_relevance_score(entry, query) if query.strip() else 1.0
                    snippet = self._generate_snippet(entry, query)
                    match_fields = self._find_match_fields(entry, query) if query.strip() else []

                    search_results.append(SearchResult(
                        entry=entry,
                        relevance_score=relevance_score,
                        snippet=snippet,
                        match_fields=match_fields
                    ))

                # Sort by relevance if requested
                if sort_by == "relevance" and query.strip():
                    search_results.sort(
                        key=lambda x: x.relevance_score,
                        reverse=(sort_order.lower() == "desc")
                    )

                return search_results, total_count

        except Exception as e:
            logger.error(f"Error executing search query: {e}")
            raise

    def _build_search_conditions(self, query: str) -> List:
        """Build SQLAlchemy search conditions for full-text search."""
        conditions = []
        search_term = f"%{query}%"

        # Search in title
        conditions.append(NotebookEntry.title.ilike(search_term))

        # Search in protocol
        conditions.append(NotebookEntry.protocol.ilike(search_term))

        # Search in tags (JSON array)
        conditions.append(
            func.json_extract_path_text(NotebookEntry.tags, '$').ilike(search_term)
        )

        # Search in cooking method
        conditions.append(NotebookEntry.cooking_method.ilike(search_term))

        # Search in observations (JSON array)
        conditions.append(
            func.json_extract_path_text(NotebookEntry.observations, '$').ilike(search_term)
        )

        # Search in outcomes (JSON object)
        conditions.append(
            func.json_extract_path_text(NotebookEntry.outcomes, '$').ilike(search_term)
        )

        # Search in gear IDs
        conditions.append(
            func.json_extract_path_text(NotebookEntry.gear_ids, '$').ilike(search_term)
        )

        return conditions

    def _build_filter_conditions(self, filters: SearchFilter) -> List:
        """Build SQLAlchemy filter conditions."""
        conditions = []

        if filters.cooking_method:
            conditions.append(NotebookEntry.cooking_method == filters.cooking_method)

        if filters.difficulty_min is not None:
            conditions.append(NotebookEntry.difficulty_level >= filters.difficulty_min)

        if filters.difficulty_max is not None:
            conditions.append(NotebookEntry.difficulty_level <= filters.difficulty_max)

        if filters.servings_min is not None:
            conditions.append(NotebookEntry.servings >= filters.servings_min)

        if filters.servings_max is not None:
            conditions.append(NotebookEntry.servings <= filters.servings_max)

        if filters.date_from:
            conditions.append(NotebookEntry.date >= filters.date_from)

        if filters.date_to:
            conditions.append(NotebookEntry.date <= filters.date_to)

        if filters.has_rating:
            conditions.append(
                func.json_extract_path_text(NotebookEntry.outcomes, 'rating_10').isnot(None)
            )

        if filters.tags:
            # Check if any of the specified tags are present
            tag_conditions = []
            for tag in filters.tags:
                tag_conditions.append(
                    func.json_extract_path_text(NotebookEntry.tags, '$').like(f'%"{tag}"%')
                )
            if tag_conditions:
                conditions.append(or_(*tag_conditions))

        return conditions

    def _add_sorting(self, query, sort_by: str, sort_order: str):
        """Add sorting to the query."""
        sort_column = NotebookEntry.date  # Default

        if sort_by == "title":
            sort_column = NotebookEntry.title
        elif sort_by == "date":
            sort_column = NotebookEntry.date
        elif sort_by == "difficulty":
            sort_column = NotebookEntry.difficulty_level
        elif sort_by == "rating":
            # Sort by rating in outcomes JSON
            sort_column = func.cast(
                func.json_extract_path_text(NotebookEntry.outcomes, 'rating_10'),
                'float'
            )
        elif sort_by == "view_count":
            sort_column = NotebookEntry.view_count

        if sort_order.lower() == "asc":
            return query.order_by(asc(sort_column))
        else:
            return query.order_by(desc(sort_column))

    def _calculate_relevance_score(self, entry: NotebookEntry, query: str) -> float:
        """Calculate relevance score for a search result."""
        if not query:
            return 1.0

        score = 0.0
        query_lower = query.lower()

        # Title matches (highest weight)
        if query_lower in entry.title.lower():
            score += 10.0
            if entry.title.lower().startswith(query_lower):
                score += 5.0  # Bonus for prefix match

        # Tag matches (high weight)
        if entry.tags:
            for tag in entry.tags:
                if query_lower in tag.lower():
                    score += 5.0

        # Cooking method match (medium weight)
        if entry.cooking_method and query_lower in entry.cooking_method.lower():
            score += 3.0

        # Protocol content matches (medium weight)
        if entry.protocol and query_lower in entry.protocol.lower():
            score += 2.0
            # Count number of matches
            matches = entry.protocol.lower().count(query_lower)
            score += min(matches * 0.5, 3.0)  # Cap at 3 extra points

        # Observations matches (low weight)
        if entry.observations:
            for obs in entry.observations:
                if isinstance(obs, dict) and obs.get("note"):
                    if query_lower in obs["note"].lower():
                        score += 1.0

        # Outcomes matches (low weight)
        if entry.outcomes:
            outcomes_text = str(entry.outcomes).lower()
            if query_lower in outcomes_text:
                score += 1.0

        # Boost for recent entries
        days_old = (datetime.now().date() - entry.date.date()).days
        if days_old < 30:
            score += 2.0
        elif days_old < 90:
            score += 1.0

        # Boost for popular entries
        if entry.view_count > 10:
            score += 1.0
        if entry.view_count > 50:
            score += 2.0

        return max(score, 0.1)  # Minimum score

    def _generate_snippet(self, entry: NotebookEntry, query: str, max_length: int = 200) -> str:
        """Generate a search result snippet."""
        if not query:
            # No query, use protocol or first observation
            if entry.protocol:
                return self._truncate_text(entry.protocol, max_length)
            elif entry.observations:
                for obs in entry.observations:
                    if isinstance(obs, dict) and obs.get("note"):
                        return self._truncate_text(obs["note"], max_length)
            return f"Entry from {entry.date.strftime('%Y-%m-%d')}"

        query_lower = query.lower()

        # Try to find snippet with query match
        sources = []

        # Check title
        if query_lower in entry.title.lower():
            sources.append(("title", entry.title))

        # Check protocol
        if entry.protocol and query_lower in entry.protocol.lower():
            sources.append(("protocol", entry.protocol))

        # Check observations
        if entry.observations:
            for obs in entry.observations:
                if isinstance(obs, dict) and obs.get("note"):
                    if query_lower in obs["note"].lower():
                        sources.append(("observation", obs["note"]))

        # Find best snippet
        for source_type, text in sources:
            snippet = self._extract_snippet_around_match(text, query, max_length)
            if snippet:
                return snippet

        # Fallback to protocol or description
        if entry.protocol:
            return self._truncate_text(entry.protocol, max_length)

        return f"Entry from {entry.date.strftime('%Y-%m-%d')}"

    def _extract_snippet_around_match(self, text: str, query: str, max_length: int) -> str:
        """Extract snippet around the query match."""
        if not text or not query:
            return ""

        text_lower = text.lower()
        query_lower = query.lower()

        # Find first match position
        match_pos = text_lower.find(query_lower)
        if match_pos == -1:
            return self._truncate_text(text, max_length)

        # Calculate snippet bounds
        snippet_start = max(0, match_pos - max_length // 3)
        snippet_end = min(len(text), snippet_start + max_length)

        # Adjust start to word boundary if possible
        if snippet_start > 0:
            space_pos = text.rfind(' ', 0, snippet_start + 20)
            if space_pos > snippet_start - 20:
                snippet_start = space_pos + 1

        # Adjust end to word boundary if possible
        if snippet_end < len(text):
            space_pos = text.find(' ', snippet_end - 20)
            if space_pos != -1 and space_pos < snippet_end + 20:
                snippet_end = space_pos

        snippet = text[snippet_start:snippet_end].strip()

        # Add ellipsis if truncated
        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."

        return snippet

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to maximum length."""
        if not text or len(text) <= max_length:
            return text

        # Try to truncate at word boundary
        truncated = text[:max_length]
        space_pos = truncated.rfind(' ')

        if space_pos > max_length * 0.8:  # If we can keep most of the text
            truncated = truncated[:space_pos]

        return truncated.strip() + "..."

    def _find_match_fields(self, entry: NotebookEntry, query: str) -> List[str]:
        """Find which fields contained the search query."""
        if not query:
            return []

        match_fields = []
        query_lower = query.lower()

        if query_lower in entry.title.lower():
            match_fields.append("title")

        if entry.protocol and query_lower in entry.protocol.lower():
            match_fields.append("protocol")

        if entry.tags:
            for tag in entry.tags:
                if query_lower in tag.lower():
                    match_fields.append("tags")
                    break

        if entry.cooking_method and query_lower in entry.cooking_method.lower():
            match_fields.append("cooking_method")

        if entry.observations:
            for obs in entry.observations:
                if isinstance(obs, dict) and obs.get("note"):
                    if query_lower in obs["note"].lower():
                        match_fields.append("observations")
                        break

        if entry.outcomes:
            outcomes_text = str(entry.outcomes).lower()
            if query_lower in outcomes_text:
                match_fields.append("outcomes")

        return match_fields

    def _generate_cache_key(
        self,
        query: str,
        filters: Optional[SearchFilter],
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str
    ) -> str:
        """Generate cache key for search parameters."""
        import hashlib

        # Create deterministic string from parameters
        filter_str = ""
        if filters:
            filter_str = str(sorted(filters.__dict__.items()))

        cache_string = f"{query}|{filter_str}|{limit}|{offset}|{sort_by}|{sort_order}"

        # Return hash of the string
        return hashlib.md5(cache_string.encode()).hexdigest()

    def _cleanup_cache(self) -> None:
        """Clean up old cache entries."""
        if len(self._search_cache) <= 100:  # Only cleanup if cache is large
            return

        current_time = time.time()
        expired_keys = [
            key for key, value in self._search_cache.items()
            if current_time - value["timestamp"] > self._cache_ttl
        ]

        for key in expired_keys:
            del self._search_cache[key]

        # If still too large, remove oldest entries
        if len(self._search_cache) > 100:
            sorted_items = sorted(
                self._search_cache.items(),
                key=lambda x: x[1]["timestamp"]
            )
            for key, _ in sorted_items[:20]:  # Remove oldest 20
                del self._search_cache[key]

    def clear_cache(self) -> None:
        """Clear the search cache."""
        self._search_cache.clear()
        logger.info("Search cache cleared")

    async def get_popular_tags(self, limit: int = 20) -> List[Tuple[str, int]]:
        """
        Get most popular tags across all entries.

        Args:
            limit: Maximum number of tags to return

        Returns:
            List of (tag, count) tuples sorted by popularity
        """
        try:
            async with get_session() as session:
                # This is a simplified approach - in production you might want
                # to use a proper tag aggregation table
                result = await session.execute(
                    select(NotebookEntry.tags)
                    .where(NotebookEntry.tags.isnot(None))
                )
                entries = result.fetchall()

                # Count tags
                tag_counts = {}
                for (tags,) in entries:
                    if tags:
                        for tag in tags:
                            tag_counts[tag] = tag_counts.get(tag, 0) + 1

                # Sort by count and return top tags
                popular_tags = sorted(
                    tag_counts.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:limit]

                return popular_tags

        except Exception as e:
            logger.error(f"Error getting popular tags: {e}")
            return []

    async def get_search_suggestions(self, query_prefix: str, limit: int = 10) -> List[str]:
        """
        Get search suggestions based on query prefix.

        Args:
            query_prefix: Partial query to get suggestions for
            limit: Maximum number of suggestions

        Returns:
            List of suggested search terms
        """
        try:
            if len(query_prefix) < 2:
                return []

            suggestions = set()
            prefix_lower = query_prefix.lower()

            async with get_session() as session:
                # Get matching titles
                result = await session.execute(
                    select(NotebookEntry.title)
                    .where(NotebookEntry.title.ilike(f"%{query_prefix}%"))
                    .limit(limit)
                )
                titles = result.scalars().all()

                for title in titles:
                    if prefix_lower in title.lower():
                        suggestions.add(title)

                # Get matching tags
                result = await session.execute(
                    select(NotebookEntry.tags)
                    .where(NotebookEntry.tags.isnot(None))
                )
                tag_entries = result.fetchall()

                for (tags,) in tag_entries:
                    if tags:
                        for tag in tags:
                            if prefix_lower in tag.lower():
                                suggestions.add(tag)

                # Get matching cooking methods
                result = await session.execute(
                    select(NotebookEntry.cooking_method)
                    .where(NotebookEntry.cooking_method.ilike(f"%{query_prefix}%"))
                    .distinct()
                )
                methods = result.scalars().all()

                for method in methods:
                    if method and prefix_lower in method.lower():
                        suggestions.add(method)

            # Return sorted suggestions
            return sorted(list(suggestions))[:limit]

        except Exception as e:
            logger.error(f"Error getting search suggestions: {e}")
            return []