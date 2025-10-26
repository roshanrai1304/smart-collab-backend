"""
Feedback learning system for Smart Collaborative Backend.

Implements adaptive improvement based on user interactions and feedback.
"""

import json
import logging
import time
import uuid
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, Counter

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class FeedbackType:
    """Types of feedback that can be collected."""
    SUMMARY_QUALITY = "summary_quality"
    TAG_RELEVANCE = "tag_relevance"
    SEARCH_RELEVANCE = "search_relevance"
    CONTENT_TYPE_ACCURACY = "content_type_accuracy"
    PROCESSING_SPEED = "processing_speed"
    OVERALL_SATISFACTION = "overall_satisfaction"


# UserFeedback model is defined in apps.ai_services.models


class FeedbackLearningSystem:
    """
    System for collecting, analyzing, and applying user feedback to improve AI performance.
    """
    
    def __init__(self):
        self.feedback_cache_timeout = 3600  # 1 hour
        self.learning_cache_timeout = 86400  # 24 hours
        
    def record_feedback(
        self,
        user: User,
        document_id: str,
        feedback_type: str,
        rating: int,
        comment: str = "",
        feedback_data: Dict[str, Any] = None,
        ai_metadata_id: str = None
    ):
        """
        Record user feedback on AI processing results.
        
        Args:
            user: User providing feedback
            document_id: Document ID
            feedback_type: Type of feedback
            rating: Rating (1-5)
            comment: Optional comment
            feedback_data: Specific feedback details
            ai_metadata_id: Associated AI metadata ID
            
        Returns:
            Created UserFeedback instance
        """
        from apps.documents.models import Document
        from apps.ai_services.models import AIDocumentMetadata
        
        from apps.ai_services.models import UserFeedback
        
        try:
            document = Document.objects.get(id=document_id)
            ai_metadata = None
            
            if ai_metadata_id:
                try:
                    ai_metadata = AIDocumentMetadata.objects.get(id=ai_metadata_id)
                except AIDocumentMetadata.DoesNotExist:
                    pass
            
            feedback = UserFeedback.objects.create(
                user=user,
                document=document,
                feedback_type=feedback_type,
                rating=rating,
                comment=comment,
                feedback_data=feedback_data or {},
                ai_metadata=ai_metadata,
                model_version=ai_metadata.model_version if ai_metadata else "",
                processing_time_ms=ai_metadata.processing_time_ms if ai_metadata else None
            )
            
            # Trigger learning update
            self._update_learning_cache(feedback_type)
            
            logger.info(f"Recorded feedback: {user.username} rated {feedback_type} as {rating}/5")
            return feedback
            
        except Exception as e:
            logger.error(f"Failed to record feedback: {str(e)}")
            raise
    
    def get_feedback_summary(
        self,
        feedback_type: str = None,
        user_id: str = None,
        time_range_days: int = 30
    ) -> Dict[str, Any]:
        """
        Get summary of feedback for analysis.
        
        Args:
            feedback_type: Filter by feedback type
            user_id: Filter by user
            time_range_days: Time range for feedback
            
        Returns:
            Feedback summary statistics
        """
        cache_key = f"feedback_summary:{feedback_type}:{user_id}:{time_range_days}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        from apps.ai_services.models import UserFeedback
        
        # Build query
        queryset = UserFeedback.objects.all()
        
        if feedback_type:
            queryset = queryset.filter(feedback_type=feedback_type)
        
        if user_id:
            queryset = queryset.filter(user_id=user_id)
        
        if time_range_days:
            since_date = timezone.now() - timedelta(days=time_range_days)
            queryset = queryset.filter(created_at__gte=since_date)
        
        # Calculate statistics
        feedback_list = list(queryset.values(
            'feedback_type', 'rating', 'model_version', 'processing_time_ms'
        ))
        
        if not feedback_list:
            return {'total_feedback': 0}
        
        # Group by feedback type
        by_type = defaultdict(list)
        for fb in feedback_list:
            by_type[fb['feedback_type']].append(fb)
        
        summary = {
            'total_feedback': len(feedback_list),
            'time_range_days': time_range_days,
            'by_type': {}
        }
        
        for ftype, ratings in by_type.items():
            rating_values = [r['rating'] for r in ratings]
            processing_times = [r['processing_time_ms'] for r in ratings if r['processing_time_ms']]
            
            type_summary = {
                'count': len(ratings),
                'average_rating': sum(rating_values) / len(rating_values),
                'rating_distribution': dict(Counter(rating_values)),
                'model_versions': list(set(r['model_version'] for r in ratings if r['model_version']))
            }
            
            if processing_times:
                type_summary['average_processing_time_ms'] = sum(processing_times) / len(processing_times)
            
            summary['by_type'][ftype] = type_summary
        
        # Cache result
        cache.set(cache_key, summary, self.feedback_cache_timeout)
        return summary
    
    def get_improvement_recommendations(self) -> Dict[str, Any]:
        """
        Analyze feedback to generate improvement recommendations.
        
        Returns:
            Dictionary with improvement recommendations
        """
        cache_key = "ai_improvement_recommendations"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        # Get recent feedback summary
        summary = self.get_feedback_summary(time_range_days=7)
        
        recommendations = {
            'priority_areas': [],
            'model_performance': {},
            'processing_optimizations': [],
            'user_satisfaction_trends': {}
        }
        
        if summary['total_feedback'] == 0:
            return recommendations
        
        # Analyze each feedback type
        for ftype, stats in summary['by_type'].items():
            avg_rating = stats['average_rating']
            
            # Identify areas needing improvement (rating < 3.5)
            if avg_rating < 3.5:
                recommendations['priority_areas'].append({
                    'area': ftype,
                    'current_rating': avg_rating,
                    'feedback_count': stats['count'],
                    'urgency': 'high' if avg_rating < 3.0 else 'medium'
                })
            
            # Model performance analysis
            if len(stats['model_versions']) > 1:
                # Compare model performance (simplified)
                recommendations['model_performance'][ftype] = {
                    'models_used': stats['model_versions'],
                    'recommendation': 'Consider A/B testing different models'
                }
            
            # Processing time analysis
            if 'average_processing_time_ms' in stats:
                if stats['average_processing_time_ms'] > 10000:  # > 10 seconds
                    recommendations['processing_optimizations'].append({
                        'area': ftype,
                        'current_time_ms': stats['average_processing_time_ms'],
                        'recommendation': 'Consider chunking or model optimization'
                    })
        
        # Cache recommendations
        cache.set(cache_key, recommendations, self.learning_cache_timeout)
        return recommendations
    
    def get_user_preferences(self, user_id: str) -> Dict[str, Any]:
        """
        Learn user preferences from their feedback history.
        
        Args:
            user_id: User ID
            
        Returns:
            User preference profile
        """
        cache_key = f"user_preferences:{user_id}"
        cached_result = cache.get(cache_key)
        
        if cached_result:
            return cached_result
        
        from apps.ai_services.models import UserFeedback
        
        # Get user's feedback history
        user_feedback = UserFeedback.objects.filter(
            user_id=user_id,
            created_at__gte=timezone.now() - timedelta(days=90)
        ).values('feedback_type', 'rating', 'feedback_data', 'comment')
        
        if not user_feedback:
            return {'has_preferences': False}
        
        preferences = {
            'has_preferences': True,
            'feedback_patterns': {},
            'content_preferences': {},
            'quality_expectations': {}
        }
        
        # Analyze feedback patterns
        by_type = defaultdict(list)
        for fb in user_feedback:
            by_type[fb['feedback_type']].append(fb)
        
        for ftype, feedback_list in by_type.items():
            ratings = [fb['rating'] for fb in feedback_list]
            avg_rating = sum(ratings) / len(ratings)
            
            preferences['feedback_patterns'][ftype] = {
                'average_rating': avg_rating,
                'feedback_count': len(feedback_list),
                'expectation_level': 'high' if avg_rating > 4.0 else 'standard'
            }
            
            # Analyze specific preferences from feedback_data
            feedback_details = [fb['feedback_data'] for fb in feedback_list if fb['feedback_data']]
            if feedback_details:
                preferences['content_preferences'][ftype] = self._analyze_content_preferences(
                    feedback_details
                )
        
        # Cache preferences
        cache.set(cache_key, preferences, self.learning_cache_timeout)
        return preferences
    
    def _analyze_content_preferences(self, feedback_details: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze specific content preferences from feedback data.
        
        Args:
            feedback_details: List of feedback data dictionaries
            
        Returns:
            Content preference analysis
        """
        preferences = {
            'preferred_summary_length': 'medium',
            'preferred_tag_count': 8,
            'content_focus': 'balanced'
        }
        
        # Analyze summary preferences
        summary_prefs = []
        tag_prefs = []
        
        for details in feedback_details:
            if 'preferred_summary_length' in details:
                summary_prefs.append(details['preferred_summary_length'])
            
            if 'preferred_tag_count' in details:
                tag_prefs.append(details['preferred_tag_count'])
        
        if summary_prefs:
            preferences['preferred_summary_length'] = Counter(summary_prefs).most_common(1)[0][0]
        
        if tag_prefs:
            preferences['preferred_tag_count'] = sum(tag_prefs) // len(tag_prefs)
        
        return preferences
    
    def apply_user_preferences(
        self,
        user_id: str,
        processing_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Apply learned user preferences to processing parameters.
        
        Args:
            user_id: User ID
            processing_params: Base processing parameters
            
        Returns:
            Adjusted processing parameters
        """
        preferences = self.get_user_preferences(user_id)
        
        if not preferences.get('has_preferences'):
            return processing_params
        
        adjusted_params = processing_params.copy()
        
        # Apply content preferences
        content_prefs = preferences.get('content_preferences', {})
        
        if FeedbackType.SUMMARY_QUALITY in content_prefs:
            summary_prefs = content_prefs[FeedbackType.SUMMARY_QUALITY]
            
            if summary_prefs.get('preferred_summary_length') == 'short':
                adjusted_params['max_summary_length'] = 100
            elif summary_prefs.get('preferred_summary_length') == 'long':
                adjusted_params['max_summary_length'] = 300
        
        if FeedbackType.TAG_RELEVANCE in content_prefs:
            tag_prefs = content_prefs[FeedbackType.TAG_RELEVANCE]
            preferred_count = tag_prefs.get('preferred_tag_count', 8)
            adjusted_params['max_tags'] = min(max(preferred_count, 3), 15)  # Clamp between 3-15
        
        # Apply quality expectations
        quality_expectations = preferences.get('quality_expectations', {})
        
        # If user has high expectations, use higher quality models
        high_expectation_types = [
            ftype for ftype, pattern in preferences.get('feedback_patterns', {}).items()
            if pattern.get('expectation_level') == 'high'
        ]
        
        if high_expectation_types:
            adjusted_params['use_quality_models'] = True
            adjusted_params['high_expectation_areas'] = high_expectation_types
        
        return adjusted_params
    
    def _update_learning_cache(self, feedback_type: str):
        """
        Update learning cache when new feedback is received.
        
        Args:
            feedback_type: Type of feedback received
        """
        # Invalidate relevant caches
        cache_patterns = [
            f"feedback_summary:{feedback_type}:*",
            "ai_improvement_recommendations",
            "user_preferences:*"
        ]
        
        # Note: In production, you'd want a more sophisticated cache invalidation
        # For now, we'll just delete the main recommendation cache
        cache.delete("ai_improvement_recommendations")
    
    def get_team_feedback_trends(self, team_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get feedback trends for a specific team.
        
        Args:
            team_id: Team ID
            days: Number of days to analyze
            
        Returns:
            Team feedback trends
        """
        from apps.documents.models import Document
        
        # Get documents for this team
        team_documents = Document.objects.filter(team_id=team_id)
        
        from apps.ai_services.models import UserFeedback
        
        # Get feedback for these documents
        feedback = UserFeedback.objects.filter(
            document__in=team_documents,
            created_at__gte=timezone.now() - timedelta(days=days)
        ).values('feedback_type', 'rating', 'created_at')
        
        if not feedback:
            return {'has_data': False}
        
        # Analyze trends
        trends = {
            'has_data': True,
            'total_feedback': len(feedback),
            'average_satisfaction': sum(fb['rating'] for fb in feedback) / len(feedback),
            'feedback_by_type': {},
            'trend_direction': 'stable'
        }
        
        # Group by type
        by_type = defaultdict(list)
        for fb in feedback:
            by_type[fb['feedback_type']].append(fb)
        
        for ftype, fb_list in by_type.items():
            ratings = [fb['rating'] for fb in fb_list]
            trends['feedback_by_type'][ftype] = {
                'count': len(fb_list),
                'average_rating': sum(ratings) / len(ratings),
                'latest_ratings': ratings[-5:]  # Last 5 ratings for trend analysis
            }
        
        return trends


# Global feedback learning system instance
_feedback_system = None


def get_feedback_system() -> FeedbackLearningSystem:
    """
    Get singleton FeedbackLearningSystem instance.
    
    Returns:
        FeedbackLearningSystem instance
    """
    global _feedback_system
    if _feedback_system is None:
        _feedback_system = FeedbackLearningSystem()
    return _feedback_system
