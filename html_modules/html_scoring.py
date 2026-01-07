#!/usr/bin/env python
"""
Score and badge system module for red-arch.
Handles dynamic score ranges, badge classes, and score-based styling.
"""

from typing import Dict, List, Any, Union

def get_score_badge_class_dynamic(score: Union[int, str], score_ranges: Dict[str, float]) -> str:
    """Return appropriate badge class based on dynamic score ranges"""
    try:
        score_int = int(score)
        
        # Handle zero and negative scores first
        if score_int < 0:
            return 'badge-danger'   # Negative - red
        elif score_int == 0:
            return 'badge-warning-orange' # Zero - orange
        
        # Use dynamic ranges for positive scores
        if score_int >= score_ranges['very_high']:
            return 'badge-success-bright'  # Very high - bright green
        elif score_int >= score_ranges['high']:
            return 'badge-success'  # High - green  
        elif score_int >= score_ranges['medium']:
            return 'badge-light'    # Medium - white/light
        else:
            return 'badge-warning'  # Low positive - yellow
            
    except (ValueError, TypeError):
        return 'badge-secondary'    # Default for invalid scores

def calculate_score_ranges(scores: List[Union[int, float]]) -> Dict[str, float]:
    """Calculate dynamic score ranges based on actual score distribution"""
    valid_positive_scores = []
    for score in scores:
        try:
            score_int = int(score)
            if score_int > 0:  # Only consider positive scores for dynamic ranges
                valid_positive_scores.append(score_int)
        except (ValueError, TypeError):
            continue
    
    if len(valid_positive_scores) == 0:
        # Fallback to minimal ranges if no positive scores
        return {'very_high': 1, 'high': 1, 'medium': 1}
    
    valid_positive_scores.sort(reverse=True)
    total_scores = len(valid_positive_scores)
    
    # Calculate percentile-based thresholds for positive scores
    very_high_idx = max(0, int(total_scores * 0.1))  # Top 10%
    high_idx = max(0, int(total_scores * 0.3))       # Top 30%
    medium_idx = max(0, int(total_scores * 0.6))     # Top 60%
    
    return {
        'very_high': valid_positive_scores[very_high_idx] if very_high_idx < len(valid_positive_scores) else valid_positive_scores[-1],
        'high': valid_positive_scores[high_idx] if high_idx < len(valid_positive_scores) else valid_positive_scores[-1],
        'medium': valid_positive_scores[medium_idx] if medium_idx < len(valid_positive_scores) else valid_positive_scores[-1]
    }

def get_score_badge_class_subreddit_global(score: Union[int, str], subreddit_score_ranges: Dict[str, float]) -> str:
    """Return appropriate badge class based on subreddit-wide score ranges"""
    try:
        score_int = int(score)
        
        # Handle zero and negative scores first
        if score_int < 0:
            return 'badge-danger'   # Negative - red
        elif score_int == 0:
            return 'badge-warning-orange' # Zero - orange
        
        # Use subreddit-global ranges for positive scores
        if score_int >= subreddit_score_ranges['very_high']:
            return 'badge-success-bright'  # Very high - bright green
        elif score_int >= subreddit_score_ranges['high']:
            return 'badge-success'  # High - green  
        elif score_int >= subreddit_score_ranges['medium']:
            return 'badge-light'    # Medium - white
        else:
            return 'badge-warning'  # Low positive - yellow
            
    except (ValueError, TypeError):
        return 'badge-secondary'    # Default for invalid scores

def calculate_subreddit_score_ranges(links: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate subreddit-wide score ranges based on all posts in the subreddit"""
    valid_positive_scores = []
    for link in links:
        try:
            score_int = int(link['score']) if isinstance(link['score'], str) and link['score'] != '' else link['score'] if isinstance(link['score'], int) else 0
            if score_int > 0:  # Only consider positive scores for dynamic ranges
                valid_positive_scores.append(score_int)
        except (ValueError, TypeError):
            continue
    
    if len(valid_positive_scores) == 0:
        # Fallback to minimal ranges if no positive scores
        return {'very_high': 1, 'high': 1, 'medium': 1}
    
    valid_positive_scores.sort(reverse=True)
    total_scores = len(valid_positive_scores)
    
    # Calculate percentile-based thresholds for positive scores
    very_high_idx = max(0, int(total_scores * 0.05))  # Top 5%
    high_idx = max(0, int(total_scores * 0.15))       # Top 15%
    medium_idx = max(0, int(total_scores * 0.40))     # Top 40%
    
    return {
        'very_high': valid_positive_scores[very_high_idx] if very_high_idx < len(valid_positive_scores) else valid_positive_scores[-1],
        'high': valid_positive_scores[high_idx] if high_idx < len(valid_positive_scores) else valid_positive_scores[-1],
        'medium': valid_positive_scores[medium_idx] if medium_idx < len(valid_positive_scores) else valid_positive_scores[-1]
    }
