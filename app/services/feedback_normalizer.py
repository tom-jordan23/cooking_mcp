"""
Unified feedback normalization service.

Standardizes feedback data from all channels (Slack, Telegram, WhatsApp, SMS,
Email, Signal) into consistent format for MCP server integration and analytics.
"""

import re
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union, Tuple
from enum import Enum

from pydantic import BaseModel, Field, validator

from ..utils.logging import get_logger
from ..services.feedback_service import FeedbackChannel


logger = get_logger(__name__)


class FeedbackConfidence(str, Enum):
    """Confidence levels for extracted feedback."""
    HIGH = "high"      # 90-100% - Explicit rating and clear text
    MEDIUM = "medium"  # 70-90% - Either rating or sentiment detected
    LOW = "low"        # 50-70% - Weak sentiment or ambiguous
    UNKNOWN = "unknown"  # <50% - Unable to determine meaningful feedback


class NormalizedRating(BaseModel):
    """Normalized rating with confidence."""
    value: int = Field(..., ge=1, le=10, description="Rating on 1-10 scale")
    confidence: FeedbackConfidence = Field(..., description="Extraction confidence")
    source: str = Field(..., description="How rating was derived")
    raw_value: Optional[str] = Field(None, description="Original raw input")


class NormalizedFeedback(BaseModel):
    """Unified normalized feedback structure."""

    # Core identifiers
    entry_id: Optional[str] = Field(None, description="Lab notebook entry ID")
    user_id: str = Field(..., description="Anonymized user identifier")
    channel: FeedbackChannel = Field(..., description="Source channel")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Feedback content
    rating: Optional[NormalizedRating] = Field(None, description="Standardized rating")
    sentiment_score: Optional[float] = Field(None, ge=-1.0, le=1.0, description="Sentiment analysis score")

    # Text content
    original_text: str = Field(..., description="Original message content")
    cleaned_text: Optional[str] = Field(None, description="Cleaned, normalized text")
    key_phrases: List[str] = Field(default_factory=list, description="Extracted key phrases")

    # Structured data
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Extracted metrics")
    categories: List[str] = Field(default_factory=list, description="Feedback categories")

    # Quality indicators
    overall_confidence: FeedbackConfidence = Field(..., description="Overall confidence")
    processing_notes: List[str] = Field(default_factory=list, description="Processing insights")

    # Channel-specific metadata
    channel_metadata: Dict[str, Any] = Field(default_factory=dict, description="Channel-specific data")


class FeedbackNormalizer:
    """Service for normalizing feedback across all channels."""

    def __init__(self):
        """Initialize feedback normalizer."""
        self.logger = get_logger(__name__)

        # Rating extraction patterns (ordered by specificity)
        self.rating_patterns = [
            # Explicit rating patterns
            (r'\b(\d{1,2})\s*(?:out\s*of\s*|\/)?\s*10\b', "explicit_scale"),
            (r'\brat(?:e|ed|ing)[\s:]*(\d{1,2})\b', "explicit_rating"),
            (r'\bscore[\s:]*(\d{1,2})\b', "explicit_score"),
            (r'\bgive\s+it\s+(?:a\s+)?(\d{1,2})\b', "explicit_give"),

            # Star-based ratings
            (r'(\d{1,2})\s*(?:stars?|⭐|★)', "star_rating"),
            (r'(⭐|★){1,10}', "emoji_stars"),

            # Contextual ratings
            (r'\b(\d{1,2})\s*(?:/|out of)?\s*(?:5|10)?\b', "numeric_context"),
        ]

        # Sentiment word mappings
        self.sentiment_words = {
            # Excellent (9-10)
            "excellent": 9.5, "perfect": 10, "amazing": 9.5, "outstanding": 9.5,
            "fantastic": 9, "wonderful": 9, "superb": 9.5, "exceptional": 9.5,
            "incredible": 9, "phenomenal": 9.5, "spectacular": 9,

            # Very Good (8-9)
            "delicious": 8.5, "great": 8.5, "awesome": 8.5, "brilliant": 8.5,
            "lovely": 8, "beautiful": 8, "marvelous": 8.5, "terrific": 8.5,

            # Good (7-8)
            "good": 7.5, "nice": 7, "tasty": 7.5, "enjoyable": 7.5,
            "pleasant": 7, "satisfying": 7.5, "solid": 7, "decent": 6.5,

            # Okay/Average (5-7)
            "okay": 6, "ok": 6, "fine": 6, "alright": 6, "average": 5.5,
            "acceptable": 6, "reasonable": 6, "fair": 5.5,

            # Poor (3-5)
            "bad": 4, "poor": 3.5, "disappointing": 4, "mediocre": 4.5,
            "bland": 4, "boring": 4, "meh": 4.5, "so-so": 5,

            # Very Poor (1-3)
            "terrible": 2, "awful": 1.5, "horrible": 1.5, "disgusting": 1,
            "revolting": 1, "inedible": 1, "nasty": 2, "gross": 2,

            # Cooking-specific terms
            "overcooked": 3, "undercooked": 3, "burnt": 2, "dry": 3.5,
            "soggy": 3.5, "mushy": 3, "tough": 3.5, "chewy": 4,
            "crispy": 8, "tender": 8, "juicy": 8.5, "flavorful": 8,
            "seasoned": 7.5, "fresh": 7.5, "moist": 7.5
        }

        # Cooking metrics patterns
        self.metrics_patterns = {
            "internal_temp": r'\b(\d+)°?\s*(?:degrees?|°)?\s*(?:f|fahrenheit|c|celsius)?\b',
            "cook_time": r'\b(\d+)\s*(?:min(?:ute)?s?|hrs?|hours?)\b',
            "rest_time": r'\brest(?:ed)?\s*(\d+)\s*(?:min(?:ute)?s?)\b',
            "servings": r'\b(\d+)\s*(?:servings?|people|portions?)\b'
        }

        # Category keywords
        self.category_keywords = {
            "doneness": ["rare", "medium", "well", "done", "overcooked", "undercooked", "raw"],
            "seasoning": ["salty", "bland", "seasoned", "spicy", "mild", "flavorful"],
            "texture": ["crispy", "tender", "tough", "chewy", "soft", "hard", "crunchy"],
            "temperature": ["hot", "cold", "warm", "cool", "room temperature"],
            "presentation": ["beautiful", "ugly", "pretty", "messy", "neat", "appealing"],
            "portion": ["too much", "too little", "perfect amount", "huge", "tiny"]
        }

    async def normalize_feedback(
        self,
        raw_text: str,
        channel: FeedbackChannel,
        user_id: str,
        entry_id: Optional[str] = None,
        channel_metadata: Optional[Dict[str, Any]] = None
    ) -> NormalizedFeedback:
        """
        Normalize feedback from any channel into standardized format.

        Args:
            raw_text: Original feedback text
            channel: Source channel
            user_id: User identifier (hashed for privacy)
            entry_id: Optional notebook entry ID
            channel_metadata: Channel-specific metadata

        Returns:
            Normalized feedback object
        """
        try:
            self.logger.info(f"Normalizing feedback from {channel.value}: {raw_text[:50]}...")

            # Clean and preprocess text
            cleaned_text = self._clean_text(raw_text)

            # Extract rating
            rating = self._extract_rating(cleaned_text, raw_text)

            # Analyze sentiment
            sentiment_score = self._analyze_sentiment(cleaned_text)

            # Extract metrics
            metrics = self._extract_metrics(cleaned_text)

            # Categorize feedback
            categories = self._categorize_feedback(cleaned_text)

            # Extract key phrases
            key_phrases = self._extract_key_phrases(cleaned_text)

            # Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(
                rating, sentiment_score, len(key_phrases), len(cleaned_text)
            )

            # Generate processing notes
            processing_notes = self._generate_processing_notes(
                rating, sentiment_score, metrics, categories
            )

            return NormalizedFeedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=channel,
                rating=rating,
                sentiment_score=sentiment_score,
                original_text=raw_text,
                cleaned_text=cleaned_text,
                key_phrases=key_phrases,
                metrics=metrics,
                categories=categories,
                overall_confidence=overall_confidence,
                processing_notes=processing_notes,
                channel_metadata=channel_metadata or {}
            )

        except Exception as e:
            self.logger.error(f"Error normalizing feedback: {e}")
            # Return minimal normalized feedback on error
            return NormalizedFeedback(
                entry_id=entry_id,
                user_id=user_id,
                channel=channel,
                original_text=raw_text,
                overall_confidence=FeedbackConfidence.UNKNOWN,
                processing_notes=[f"Error during normalization: {str(e)}"]
            )

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text for processing."""
        # Remove excessive whitespace
        cleaned = re.sub(r'\s+', ' ', text).strip()

        # Normalize common abbreviations
        replacements = {
            r'\bu\b': 'you',
            r'\bur\b': 'your',
            r'\btho\b': 'though',
            r'\bw/\b': 'with',
            r'\bw/o\b': 'without',
            r'\btbh\b': 'to be honest',
            r'\bimo\b': 'in my opinion',
            r'\bomg\b': 'oh my god'
        }

        for pattern, replacement in replacements.items():
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        return cleaned

    def _extract_rating(self, cleaned_text: str, raw_text: str) -> Optional[NormalizedRating]:
        """Extract and normalize rating from text."""

        # Try explicit rating patterns first
        for pattern, source in self.rating_patterns:
            match = re.search(pattern, cleaned_text, re.IGNORECASE)
            if match:
                try:
                    if source == "emoji_stars":
                        # Count star emojis
                        stars = len(re.findall(r'⭐|★', match.group(0)))
                        if 1 <= stars <= 10:
                            return NormalizedRating(
                                value=stars,
                                confidence=FeedbackConfidence.HIGH,
                                source=source,
                                raw_value=match.group(0)
                            )
                    else:
                        # Extract numeric value
                        value = int(match.group(1))
                        if 1 <= value <= 10:
                            confidence = FeedbackConfidence.HIGH if source.startswith("explicit") else FeedbackConfidence.MEDIUM
                            return NormalizedRating(
                                value=value,
                                confidence=confidence,
                                source=source,
                                raw_value=match.group(0)
                            )
                except (ValueError, IndexError):
                    continue

        # Fallback to sentiment analysis
        sentiment_rating = self._sentiment_to_rating(cleaned_text)
        if sentiment_rating:
            return sentiment_rating

        return None

    def _sentiment_to_rating(self, text: str) -> Optional[NormalizedRating]:
        """Convert sentiment analysis to rating."""
        text_lower = text.lower()

        # Find sentiment words and their scores
        sentiment_scores = []
        found_words = []

        for word, score in self.sentiment_words.items():
            if word in text_lower:
                sentiment_scores.append(score)
                found_words.append(word)

        if sentiment_scores:
            # Calculate weighted average (recent words matter more)
            avg_score = sum(sentiment_scores) / len(sentiment_scores)
            rating_value = max(1, min(10, round(avg_score)))

            confidence = FeedbackConfidence.MEDIUM if len(found_words) >= 2 else FeedbackConfidence.LOW

            return NormalizedRating(
                value=rating_value,
                confidence=confidence,
                source=f"sentiment_analysis",
                raw_value=", ".join(found_words)
            )

        return None

    def _analyze_sentiment(self, text: str) -> Optional[float]:
        """Analyze sentiment and return score between -1.0 and 1.0."""
        text_lower = text.lower()

        positive_words = ["good", "great", "excellent", "amazing", "love", "delicious", "perfect", "wonderful"]
        negative_words = ["bad", "terrible", "awful", "hate", "disgusting", "horrible", "disappointing"]

        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)

        total_words = len(text_lower.split())

        if total_words == 0:
            return None

        # Calculate sentiment score
        if positive_count > 0 or negative_count > 0:
            sentiment = (positive_count - negative_count) / max(1, total_words) * 10
            return max(-1.0, min(1.0, sentiment))

        return None

    def _extract_metrics(self, text: str) -> Dict[str, Any]:
        """Extract cooking metrics from text."""
        metrics = {}

        for metric_name, pattern in self.metrics_patterns.items():
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    # Take the first numeric match
                    value = int(matches[0]) if matches[0].isdigit() else None
                    if value:
                        metrics[metric_name] = value
                except (ValueError, IndexError):
                    continue

        return metrics

    def _categorize_feedback(self, text: str) -> List[str]:
        """Categorize feedback based on content."""
        categories = []
        text_lower = text.lower()

        for category, keywords in self.category_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                categories.append(category)

        return categories

    def _extract_key_phrases(self, text: str) -> List[str]:
        """Extract key phrases from feedback."""
        # Simple key phrase extraction
        # In production, would use more sophisticated NLP

        # Split into sentences and filter meaningful ones
        sentences = re.split(r'[.!?]+', text)
        key_phrases = []

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10 and len(sentence.split()) >= 3:
                # Remove common filler words
                words = sentence.split()
                meaningful_words = [w for w in words if len(w) > 2 and w.lower() not in
                                  {'the', 'and', 'but', 'was', 'were', 'are', 'that', 'this'}]

                if len(meaningful_words) >= 2:
                    key_phrases.append(sentence)

        return key_phrases[:5]  # Limit to top 5 phrases

    def _calculate_overall_confidence(
        self,
        rating: Optional[NormalizedRating],
        sentiment_score: Optional[float],
        key_phrases_count: int,
        text_length: int
    ) -> FeedbackConfidence:
        """Calculate overall confidence in feedback normalization."""

        score = 0

        # Rating contributes most to confidence
        if rating:
            if rating.confidence == FeedbackConfidence.HIGH:
                score += 40
            elif rating.confidence == FeedbackConfidence.MEDIUM:
                score += 30
            else:
                score += 15

        # Sentiment analysis adds confidence
        if sentiment_score is not None:
            score += 25

        # Text richness indicators
        if key_phrases_count > 0:
            score += min(20, key_phrases_count * 5)

        if text_length > 50:
            score += 15
        elif text_length > 20:
            score += 10

        # Convert score to confidence level
        if score >= 80:
            return FeedbackConfidence.HIGH
        elif score >= 60:
            return FeedbackConfidence.MEDIUM
        elif score >= 40:
            return FeedbackConfidence.LOW
        else:
            return FeedbackConfidence.UNKNOWN

    def _generate_processing_notes(
        self,
        rating: Optional[NormalizedRating],
        sentiment_score: Optional[float],
        metrics: Dict[str, Any],
        categories: List[str]
    ) -> List[str]:
        """Generate processing notes for debugging and quality assurance."""
        notes = []

        if rating:
            notes.append(f"Rating extracted via {rating.source} with {rating.confidence.value} confidence")
        else:
            notes.append("No rating could be extracted")

        if sentiment_score is not None:
            sentiment_desc = "positive" if sentiment_score > 0 else "negative" if sentiment_score < 0 else "neutral"
            notes.append(f"Sentiment analysis: {sentiment_desc} ({sentiment_score:.2f})")

        if metrics:
            notes.append(f"Extracted metrics: {', '.join(metrics.keys())}")

        if categories:
            notes.append(f"Categorized as: {', '.join(categories)}")

        return notes

    async def normalize_bulk_feedback(
        self,
        feedback_list: List[Dict[str, Any]]
    ) -> List[NormalizedFeedback]:
        """Normalize multiple feedback items in bulk."""
        results = []

        for feedback_item in feedback_list:
            try:
                normalized = await self.normalize_feedback(
                    raw_text=feedback_item["text"],
                    channel=FeedbackChannel(feedback_item["channel"]),
                    user_id=feedback_item["user_id"],
                    entry_id=feedback_item.get("entry_id"),
                    channel_metadata=feedback_item.get("metadata")
                )
                results.append(normalized)
            except Exception as e:
                self.logger.error(f"Error normalizing bulk feedback item: {e}")
                continue

        return results

    def get_normalization_stats(self, normalized_feedback: List[NormalizedFeedback]) -> Dict[str, Any]:
        """Generate statistics about normalization quality."""
        if not normalized_feedback:
            return {}

        total = len(normalized_feedback)
        confidence_counts = {}
        channel_counts = {}
        rating_counts = 0
        sentiment_counts = 0

        for feedback in normalized_feedback:
            # Confidence distribution
            conf = feedback.overall_confidence.value
            confidence_counts[conf] = confidence_counts.get(conf, 0) + 1

            # Channel distribution
            channel = feedback.channel.value
            channel_counts[channel] = channel_counts.get(channel, 0) + 1

            # Feature extraction success
            if feedback.rating:
                rating_counts += 1
            if feedback.sentiment_score is not None:
                sentiment_counts += 1

        return {
            "total_feedback": total,
            "confidence_distribution": {k: v/total for k, v in confidence_counts.items()},
            "channel_distribution": channel_counts,
            "rating_extraction_rate": rating_counts / total if total > 0 else 0,
            "sentiment_analysis_rate": sentiment_counts / total if total > 0 else 0,
        }


# Global normalizer instance
feedback_normalizer = FeedbackNormalizer()