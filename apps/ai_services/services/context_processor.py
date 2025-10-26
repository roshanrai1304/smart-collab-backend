"""
Context-aware AI processing service for Smart Collaborative Backend.

Implements team and project-specific optimization for improved AI results.
"""

import logging
import json
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)


class ContextualProcessor:
    """
    Context-aware AI processor that adapts processing based on:
    - Team terminology and preferences
    - Project context and domain
    - Historical document patterns
    - User collaboration patterns
    """
    
    def __init__(self):
        self.context_cache_timeout = 3600 * 6  # 6 hours
        self.terminology_cache_timeout = 3600 * 24  # 24 hours
        
    def get_team_context(self, team_id: str) -> Dict[str, Any]:
        """
        Get contextual information about a team for AI processing optimization.
        
        Args:
            team_id: Team ID
            
        Returns:
            Team context information
        """
        cache_key = f"team_context:{team_id}"
        cached_context = cache.get(cache_key)
        
        if cached_context:
            return cached_context
        
        from apps.organizations.models import Team
        from apps.documents.models import Document
        
        try:
            team = Team.objects.get(id=team_id)
            
            # Get team documents for analysis
            team_docs = Document.objects.filter(
                team=team,
                created_at__gte=timezone.now() - timedelta(days=90)
            ).select_related('created_by')
            
            context = {
                'team_id': team_id,
                'team_name': team.name,
                'organization_name': team.organization.name,
                'document_count': team_docs.count(),
                'active_members': self._get_active_members(team_docs),
                'common_terminology': self._extract_team_terminology(team_docs),
                'content_patterns': self._analyze_content_patterns(team_docs),
                'collaboration_style': self._analyze_collaboration_style(team_docs),
                'domain_focus': self._detect_domain_focus(team_docs),
                'processing_preferences': self._get_team_processing_preferences(team_id)
            }
            
            # Cache the context
            cache.set(cache_key, context, self.context_cache_timeout)
            return context
            
        except Team.DoesNotExist:
            logger.warning(f"Team {team_id} not found")
            return {'team_id': team_id, 'error': 'Team not found'}
        except Exception as e:
            logger.error(f"Error getting team context: {str(e)}")
            return {'team_id': team_id, 'error': str(e)}
    
    def _get_active_members(self, team_docs) -> List[Dict[str, Any]]:
        """Get active team members from recent document activity."""
        member_activity = defaultdict(int)
        
        for doc in team_docs:
            member_activity[doc.created_by.id] += 1
        
        # Get top contributors
        top_contributors = sorted(
            member_activity.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        active_members = []
        for user_id, doc_count in top_contributors:
            try:
                user = User.objects.get(id=user_id)
                active_members.append({
                    'user_id': user_id,
                    'username': user.username,
                    'document_count': doc_count,
                    'full_name': f"{user.first_name} {user.last_name}".strip()
                })
            except User.DoesNotExist:
                continue
        
        return active_members
    
    def _extract_team_terminology(self, team_docs) -> Dict[str, Any]:
        """Extract common terminology and jargon used by the team."""
        # Combine all document content
        all_content = []
        for doc in team_docs[:50]:  # Limit to recent 50 docs for performance
            if doc.content_text:
                all_content.append(doc.content_text.lower())
        
        if not all_content:
            return {'terms': [], 'phrases': []}
        
        combined_text = ' '.join(all_content)
        
        # Extract common terms (simplified approach)
        words = combined_text.split()
        
        # Filter out common words and get frequent terms
        common_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have',
            'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
            'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
        }
        
        # Get terms that appear frequently and are not common words
        word_counts = Counter(word.strip('.,!?;:"()[]{}') for word in words)
        
        frequent_terms = [
            term for term, count in word_counts.most_common(100)
            if len(term) > 3 and term not in common_words and count > 2
        ]
        
        # Extract common phrases (simplified - look for repeated 2-3 word combinations)
        phrases = []
        words_clean = [w.strip('.,!?;:"()[]{}') for w in words if len(w) > 2]
        
        # 2-word phrases
        bigrams = [f"{words_clean[i]} {words_clean[i+1]}" 
                  for i in range(len(words_clean)-1)]
        bigram_counts = Counter(bigrams)
        
        common_phrases = [
            phrase for phrase, count in bigram_counts.most_common(20)
            if count > 3 and not any(word in common_words for word in phrase.split())
        ]
        
        return {
            'terms': frequent_terms[:30],  # Top 30 terms
            'phrases': common_phrases[:15],  # Top 15 phrases
            'vocabulary_size': len(set(words)),
            'total_words': len(words)
        }
    
    def _analyze_content_patterns(self, team_docs) -> Dict[str, Any]:
        """Analyze common content patterns in team documents."""
        patterns = {
            'document_types': Counter(),
            'average_length': 0,
            'common_structures': [],
            'media_usage': 0,
            'collaboration_level': 'medium'
        }
        
        if not team_docs:
            return patterns
        
        total_length = 0
        media_count = 0
        
        for doc in team_docs:
            # Document type analysis (from AI metadata if available)
            if hasattr(doc, 'ai_metadata') and doc.ai_metadata:
                if doc.ai_metadata.detected_content_type:
                    patterns['document_types'][doc.ai_metadata.detected_content_type] += 1
            
            # Length analysis
            if doc.content_text:
                total_length += len(doc.content_text)
            
            # Media usage
            if hasattr(doc, 'media_attachments'):
                media_count += doc.media_attachments.count()
        
        patterns['average_length'] = total_length // len(team_docs) if team_docs else 0
        patterns['media_usage'] = media_count / len(team_docs) if team_docs else 0
        
        # Most common document types
        patterns['primary_document_types'] = [
            doc_type for doc_type, count in patterns['document_types'].most_common(3)
        ]
        
        return patterns
    
    def _analyze_collaboration_style(self, team_docs) -> Dict[str, Any]:
        """Analyze team collaboration patterns."""
        collaboration = {
            'style': 'individual',  # individual, collaborative, mixed
            'comment_frequency': 0,
            'revision_frequency': 0,
            'shared_authorship': False
        }
        
        if not team_docs:
            return collaboration
        
        # Analyze document comments and revisions
        total_comments = 0
        total_revisions = 0
        multi_author_docs = 0
        
        for doc in team_docs:
            # Count comments if available
            if hasattr(doc, 'comments'):
                total_comments += doc.comments.count()
            
            # Count versions/revisions if available
            if hasattr(doc, 'versions'):
                total_revisions += doc.versions.count()
            
            # Check for multiple authors (simplified)
            if doc.created_by != doc.updated_by:
                multi_author_docs += 1
        
        collaboration['comment_frequency'] = total_comments / len(team_docs)
        collaboration['revision_frequency'] = total_revisions / len(team_docs)
        collaboration['shared_authorship'] = multi_author_docs / len(team_docs) > 0.3
        
        # Determine collaboration style
        if collaboration['comment_frequency'] > 2 or collaboration['shared_authorship']:
            collaboration['style'] = 'collaborative'
        elif collaboration['comment_frequency'] > 0.5:
            collaboration['style'] = 'mixed'
        
        return collaboration
    
    def _detect_domain_focus(self, team_docs) -> Dict[str, Any]:
        """Detect the primary domain/industry focus of the team."""
        domain_indicators = {
            'technology': ['api', 'software', 'code', 'development', 'system', 'database', 'server'],
            'marketing': ['campaign', 'brand', 'customer', 'market', 'sales', 'promotion', 'audience'],
            'finance': ['budget', 'revenue', 'cost', 'profit', 'investment', 'financial', 'accounting'],
            'healthcare': ['patient', 'medical', 'health', 'treatment', 'diagnosis', 'clinical'],
            'education': ['student', 'course', 'curriculum', 'learning', 'education', 'training'],
            'legal': ['contract', 'legal', 'compliance', 'regulation', 'policy', 'agreement'],
            'research': ['study', 'analysis', 'research', 'data', 'findings', 'methodology'],
            'operations': ['process', 'workflow', 'operations', 'procedure', 'logistics', 'supply']
        }
        
        # Combine all document content for analysis
        all_text = ' '.join([
            doc.content_text.lower() for doc in team_docs[:30] 
            if doc.content_text
        ])
        
        if not all_text:
            return {'primary_domain': 'general', 'confidence': 0.0}
        
        # Count domain-specific terms
        domain_scores = {}
        for domain, keywords in domain_indicators.items():
            score = sum(all_text.count(keyword) for keyword in keywords)
            domain_scores[domain] = score
        
        # Find primary domain
        if domain_scores:
            primary_domain = max(domain_scores, key=domain_scores.get)
            max_score = domain_scores[primary_domain]
            total_score = sum(domain_scores.values())
            
            confidence = max_score / total_score if total_score > 0 else 0.0
            
            return {
                'primary_domain': primary_domain if confidence > 0.3 else 'general',
                'confidence': confidence,
                'domain_scores': domain_scores
            }
        
        return {'primary_domain': 'general', 'confidence': 0.0}
    
    def _get_team_processing_preferences(self, team_id: str) -> Dict[str, Any]:
        """Get team-specific AI processing preferences from feedback."""
        from apps.ai_services.services.feedback_learning import get_feedback_system
        
        feedback_system = get_feedback_system()
        team_trends = feedback_system.get_team_feedback_trends(team_id, days=60)
        
        preferences = {
            'summary_style': 'balanced',  # concise, balanced, detailed
            'tag_preference': 'technical',  # general, technical, business
            'processing_speed': 'balanced',  # fast, balanced, quality
            'detail_level': 'medium'  # low, medium, high
        }
        
        if not team_trends.get('has_data'):
            return preferences
        
        # Analyze feedback to determine preferences
        feedback_by_type = team_trends.get('feedback_by_type', {})
        
        # Summary preferences
        if 'summary_quality' in feedback_by_type:
            summary_feedback = feedback_by_type['summary_quality']
            if summary_feedback['average_rating'] < 3.5:
                preferences['summary_style'] = 'detailed'  # They want more detail
        
        # Processing speed preferences
        if 'processing_speed' in feedback_by_type:
            speed_feedback = feedback_by_type['processing_speed']
            if speed_feedback['average_rating'] < 3.5:
                preferences['processing_speed'] = 'fast'  # They prioritize speed
        
        return preferences
    
    def optimize_processing_for_context(
        self,
        content: str,
        team_id: str,
        user_id: str = None,
        processing_params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Optimize AI processing parameters based on team and user context.
        
        Args:
            content: Document content to process
            team_id: Team ID for context
            user_id: Optional user ID for personalization
            processing_params: Base processing parameters
            
        Returns:
            Optimized processing parameters
        """
        # Get team context
        team_context = self.get_team_context(team_id)
        
        # Start with base parameters
        optimized_params = processing_params.copy() if processing_params else {}
        
        # Apply team-specific optimizations
        self._apply_team_optimizations(optimized_params, team_context, content)
        
        # Apply user-specific optimizations if user provided
        if user_id:
            from apps.ai_services.services.feedback_learning import get_feedback_system
            feedback_system = get_feedback_system()
            optimized_params = feedback_system.apply_user_preferences(user_id, optimized_params)
        
        return optimized_params
    
    def _apply_team_optimizations(
        self,
        params: Dict[str, Any],
        team_context: Dict[str, Any],
        content: str
    ):
        """Apply team-specific optimizations to processing parameters."""
        
        # Domain-specific optimizations
        domain_info = team_context.get('domain_focus', {})
        primary_domain = domain_info.get('primary_domain', 'general')
        
        if primary_domain == 'technology':
            params['preserve_technical_terms'] = True
            params['tag_focus'] = 'technical'
            params['summary_style'] = 'structured'
        elif primary_domain == 'marketing':
            params['tag_focus'] = 'business'
            params['sentiment_analysis'] = True
            params['summary_style'] = 'persuasive'
        elif primary_domain == 'research':
            params['extract_methodology'] = True
            params['summary_style'] = 'academic'
            params['key_points_focus'] = 'findings'
        
        # Terminology optimization
        terminology = team_context.get('common_terminology', {})
        if terminology.get('terms'):
            params['preserve_terms'] = terminology['terms'][:20]  # Top 20 terms
        if terminology.get('phrases'):
            params['preserve_phrases'] = terminology['phrases'][:10]  # Top 10 phrases
        
        # Content pattern optimization
        content_patterns = team_context.get('content_patterns', {})
        primary_doc_types = content_patterns.get('primary_document_types', [])
        
        if 'meeting_notes' in primary_doc_types:
            params['extract_action_items'] = True
            params['identify_participants'] = True
        elif 'technical_doc' in primary_doc_types:
            params['preserve_code_snippets'] = True
            params['technical_accuracy'] = True
        elif 'report' in primary_doc_types:
            params['structured_summary'] = True
            params['extract_metrics'] = True
        
        # Collaboration style optimization
        collaboration = team_context.get('collaboration_style', {})
        if collaboration.get('style') == 'collaborative':
            params['highlight_collaborative_elements'] = True
            params['extract_discussion_points'] = True
        
        # Processing preferences
        preferences = team_context.get('processing_preferences', {})
        
        if preferences.get('processing_speed') == 'fast':
            params['use_fast_models'] = True
            params['parallel_processing'] = True
        elif preferences.get('processing_speed') == 'quality':
            params['use_quality_models'] = True
            params['detailed_analysis'] = True
        
        if preferences.get('summary_style') == 'detailed':
            params['max_summary_length'] = params.get('max_summary_length', 200) * 1.5
        elif preferences.get('summary_style') == 'concise':
            params['max_summary_length'] = params.get('max_summary_length', 200) * 0.7
    
    def get_contextual_prompts(
        self,
        team_id: str,
        task_type: str,
        content_sample: str = ""
    ) -> Dict[str, str]:
        """
        Generate context-aware prompts for AI processing.
        
        Args:
            team_id: Team ID
            task_type: Type of AI task (summarization, tagging, etc.)
            content_sample: Sample of content for context
            
        Returns:
            Dictionary with contextual prompts
        """
        team_context = self.get_team_context(team_id)
        
        # Base prompts
        base_prompts = {
            'summarization': "Summarize the following document clearly and concisely:",
            'tagging': "Extract relevant tags from the following content:",
            'classification': "Classify the type of the following document:",
            'analysis': "Analyze the following content for key insights:"
        }
        
        # Get contextual enhancements
        domain = team_context.get('domain_focus', {}).get('primary_domain', 'general')
        terminology = team_context.get('common_terminology', {})
        
        # Enhance prompts with context
        enhanced_prompts = {}
        
        for task, base_prompt in base_prompts.items():
            if task == task_type or task_type == 'all':
                enhanced_prompt = base_prompt
                
                # Add domain context
                if domain != 'general':
                    enhanced_prompt += f" Focus on {domain}-specific aspects."
                
                # Add terminology context
                if terminology.get('terms'):
                    key_terms = ', '.join(terminology['terms'][:10])
                    enhanced_prompt += f" Pay attention to these important terms: {key_terms}."
                
                # Add team-specific instructions
                collaboration_style = team_context.get('collaboration_style', {}).get('style')
                if collaboration_style == 'collaborative' and task == 'summarization':
                    enhanced_prompt += " Highlight collaborative elements and discussion points."
                
                enhanced_prompts[task] = enhanced_prompt
        
        return enhanced_prompts if task_type == 'all' else {task_type: enhanced_prompts.get(task_type, base_prompts.get(task_type))}
    
    def invalidate_team_context(self, team_id: str):
        """
        Invalidate cached team context when team data changes.
        
        Args:
            team_id: Team ID to invalidate
        """
        cache_key = f"team_context:{team_id}"
        cache.delete(cache_key)
        logger.info(f"Invalidated team context cache for team {team_id}")


# Global contextual processor instance
_contextual_processor = None


def get_contextual_processor() -> ContextualProcessor:
    """
    Get singleton ContextualProcessor instance.
    
    Returns:
        ContextualProcessor instance
    """
    global _contextual_processor
    if _contextual_processor is None:
        _contextual_processor = ContextualProcessor()
    return _contextual_processor
