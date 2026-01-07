# ABOUTME: Auto-tuning effectiveness validation and performance comparison system for Step 4.2
# ABOUTME: Provides comprehensive validation of auto-tuning decisions and performance impact analysis

import time
import json
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from utils.console_output import print_error, print_info, print_success, print_warning


@dataclass
class PerformanceSnapshot:
    """Snapshot of system performance at a specific point in time."""
    timestamp: float
    batch_size: int
    records_per_second: float
    memory_usage_mb: float
    connection_pool_utilization: float
    auto_adjustments_count: int
    operation_type: str  # 'posts', 'comments', 'user_linking', etc.
    phase: str  # 'database_loading', 'html_generation', etc.


@dataclass
class AutoTuningComparison:
    """Comparison of performance before and after auto-tuning adjustment."""
    before_snapshot: PerformanceSnapshot
    after_snapshot: PerformanceSnapshot
    adjustment_type: str  # 'batch_size', 'connection_pool', 'memory_optimization'
    improvement_percentage: float
    effectiveness_score: float
    recommendation: str


@dataclass
class ValidationSession:
    """Complete validation session tracking multiple performance comparisons."""
    session_id: str
    start_time: float
    end_time: Optional[float] = None
    comparisons: List[AutoTuningComparison] = field(default_factory=list)
    overall_effectiveness: float = 0.0
    regression_count: int = 0
    improvement_count: int = 0


class AutoTuningValidator:
    """Advanced auto-tuning effectiveness validation and performance comparison engine."""

    def __init__(self, output_dir: str = None, enable_detailed_logging: bool = True):
        """Initialize auto-tuning validator.

        Args:
            output_dir: Directory to store validation reports
            enable_detailed_logging: Whether to enable detailed logging
        """
        self.output_dir = output_dir or os.getcwd()
        self.enable_detailed_logging = enable_detailed_logging
        self.current_session: Optional[ValidationSession] = None
        self.performance_baselines: Dict[str, PerformanceSnapshot] = {}
        self.validation_history: List[ValidationSession] = []

        # Ensure validation directory exists
        os.makedirs(os.path.join(self.output_dir, 'auto_tuning_validation'), exist_ok=True)

    def start_validation_session(self, session_id: str = None) -> str:
        """Start a new validation session.

        Args:
            session_id: Optional session identifier

        Returns:
            Session ID
        """
        if session_id is None:
            session_id = f"validation_{int(time.time())}"

        self.current_session = ValidationSession(
            session_id=session_id,
            start_time=time.time()
        )

        print_info(f"🔍 Started auto-tuning validation session: {session_id}")
        return session_id

    def capture_performance_snapshot(self, operation_type: str, phase: str = "general") -> PerformanceSnapshot:
        """Capture current performance metrics as baseline or comparison point.

        Arts:
            operation_type: Type of operation being measured
            phase: Specific phase of the operation

        Returns:
            Performance snapshot
        """
        # Get current performance metrics from various sources
        try:
            import psutil
            process = psutil.Process()
            memory_usage_mb = process.memory_info().rss / (1024 * 1024)
        except Exception:
            memory_usage_mb = 0.0

        # Try to get batch processor metrics if available
        batch_size = 1000  # Default fallback
        records_per_second = 0.0
        auto_adjustments_count = 0

        # This would typically be injected from the calling code
        # For now, we'll use defaults and update via set_current_metrics

        snapshot = PerformanceSnapshot(
            timestamp=time.time(),
            batch_size=batch_size,
            records_per_second=records_per_second,
            memory_usage_mb=memory_usage_mb,
            connection_pool_utilization=0.0,
            auto_adjustments_count=auto_adjustments_count,
            operation_type=operation_type,
            phase=phase
        )

        if self.enable_detailed_logging:
            print_info(f"📊 Performance snapshot captured: {operation_type}/{phase} - "
                      f"{records_per_second:.1f} rec/s, {memory_usage_mb:.1f}MB")

        return snapshot

    def set_current_metrics(self, batch_size: int = None, records_per_second: float = None,
                           pool_utilization: float = None, auto_adjustments: int = None):
        """Update current metrics for the next snapshot.

        Args:
            batch_size: Current batch size
            records_per_second: Current processing rate
            pool_utilization: Connection pool utilization (0.0-1.0)
            auto_adjustments: Number of auto-adjustments made
        """
        # Store metrics for next snapshot capture
        if hasattr(self, '_current_metrics'):
            self._current_metrics.update({
                k: v for k, v in {
                    'batch_size': batch_size,
                    'records_per_second': records_per_second,
                    'pool_utilization': pool_utilization,
                    'auto_adjustments': auto_adjustments
                }.items() if v is not None
            })
        else:
            self._current_metrics = {
                'batch_size': batch_size or 1000,
                'records_per_second': records_per_second or 0.0,
                'pool_utilization': pool_utilization or 0.0,
                'auto_adjustments': auto_adjustments or 0
            }

    def validate_adjustment_effectiveness(self, before_snapshot: PerformanceSnapshot,
                                        after_snapshot: PerformanceSnapshot,
                                        adjustment_type: str) -> AutoTuningComparison:
        """Validate the effectiveness of an auto-tuning adjustment.

        Args:
            before_snapshot: Performance before adjustment
            after_snapshot: Performance after adjustment
            adjustment_type: Type of adjustment made

        Returns:
            Comparison analysis with effectiveness scoring
        """
        # Calculate performance improvement percentage
        if before_snapshot.records_per_second > 0:
            speed_improvement = (
                (after_snapshot.records_per_second - before_snapshot.records_per_second) /
                before_snapshot.records_per_second * 100
            )
        else:
            speed_improvement = 0.0

        # Calculate memory efficiency improvement
        memory_change = after_snapshot.memory_usage_mb - before_snapshot.memory_usage_mb
        memory_efficiency_change = -memory_change  # Lower memory usage is better

        # Calculate overall effectiveness score (0-100)
        effectiveness_score = self._calculate_effectiveness_score(
            speed_improvement, memory_efficiency_change, adjustment_type
        )

        # Generate recommendation
        recommendation = self._generate_adjustment_recommendation(
            speed_improvement, memory_efficiency_change, effectiveness_score
        )

        comparison = AutoTuningComparison(
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            adjustment_type=adjustment_type,
            improvement_percentage=speed_improvement,
            effectiveness_score=effectiveness_score,
            recommendation=recommendation
        )

        # Add to current session if available
        if self.current_session:
            self.current_session.comparisons.append(comparison)
            if effectiveness_score >= 50:
                self.current_session.improvement_count += 1
            else:
                self.current_session.regression_count += 1

        # Log results
        if effectiveness_score >= 75:
            print_success(f"✅ Effective auto-tuning: {adjustment_type} improved performance by {speed_improvement:.1f}%")
        elif effectiveness_score >= 50:
            print_info(f"✔️  Moderate auto-tuning: {adjustment_type} - {speed_improvement:.1f}% improvement")
        else:
            print_warning(f"⚠️  Ineffective auto-tuning: {adjustment_type} - {speed_improvement:.1f}% change")

        return comparison

    def _calculate_effectiveness_score(self, speed_improvement: float,
                                     memory_efficiency_change: float,
                                     adjustment_type: str) -> float:
        """Calculate effectiveness score for an adjustment.

        Args:
            speed_improvement: Percentage improvement in processing speed
            memory_efficiency_change: Change in memory efficiency
            adjustment_type: Type of adjustment

        Returns:
            Effectiveness score (0-100)
        """
        # Base score from speed improvement
        speed_score = max(0, min(70, speed_improvement + 50))  # 0-70 points

        # Memory efficiency score
        memory_score = max(0, min(20, memory_efficiency_change + 10))  # 0-20 points

        # Adjustment type bonus/penalty
        type_modifier = {
            'batch_size': 1.0,
            'connection_pool': 1.1,  # Slightly favor connection pool adjustments
            'memory_optimization': 0.9
        }.get(adjustment_type, 1.0)

        # Stability penalty for large changes
        if abs(speed_improvement) > 50:  # Very large changes are less stable
            stability_penalty = 10
        else:
            stability_penalty = 0

        final_score = (speed_score + memory_score) * type_modifier - stability_penalty
        return max(0, min(100, final_score))

    def _generate_adjustment_recommendation(self, speed_improvement: float,
                                          memory_efficiency_change: float,
                                          effectiveness_score: float) -> str:
        """Generate recommendation based on adjustment results.

        Args:
            speed_improvement: Speed improvement percentage
            memory_efficiency_change: Memory efficiency change
            effectiveness_score: Overall effectiveness score

        Returns:
            Recommendation string
        """
        if effectiveness_score >= 75:
            return "Excellent optimization - continue with similar adjustments"
        elif effectiveness_score >= 50:
            return "Good optimization - monitor for stability"
        elif speed_improvement < -10:
            return "Performance regression detected - consider reverting adjustment"
        elif memory_efficiency_change < -20:
            return "High memory usage increase - reduce batch sizes"
        else:
            return "Minimal impact - try different optimization approach"

    def generate_session_report(self) -> Optional[Dict[str, Any]]:
        """Generate comprehensive report for current validation session.

        Returns:
            Session validation report
        """
        if not self.current_session:
            print_warning("No active validation session")
            return None

        session = self.current_session
        comparisons = session.comparisons

        if not comparisons:
            print_info("No auto-tuning comparisons recorded in session")
            return None

        # Calculate overall session metrics
        avg_effectiveness = sum(c.effectiveness_score for c in comparisons) / len(comparisons)
        avg_improvement = sum(c.improvement_percentage for c in comparisons) / len(comparisons)

        # Performance trend analysis
        trend_analysis = self._analyze_session_trends(comparisons)

        # Generate detailed report
        report = {
            'session_id': session.session_id,
            'duration_minutes': (time.time() - session.start_time) / 60,
            'total_comparisons': len(comparisons),
            'improvements': session.improvement_count,
            'regressions': session.regression_count,
            'overall_effectiveness': round(avg_effectiveness, 2),
            'average_improvement_percentage': round(avg_improvement, 2),
            'trend_analysis': trend_analysis,
            'detailed_comparisons': [
                {
                    'adjustment_type': c.adjustment_type,
                    'improvement_percentage': round(c.improvement_percentage, 2),
                    'effectiveness_score': round(c.effectiveness_score, 2),
                    'recommendation': c.recommendation,
                    'before_performance': {
                        'records_per_second': c.before_snapshot.records_per_second,
                        'memory_usage_mb': c.before_snapshot.memory_usage_mb,
                        'batch_size': c.before_snapshot.batch_size
                    },
                    'after_performance': {
                        'records_per_second': c.after_snapshot.records_per_second,
                        'memory_usage_mb': c.after_snapshot.memory_usage_mb,
                        'batch_size': c.after_snapshot.batch_size
                    }
                } for c in comparisons
            ],
            'recommendations': self._generate_session_recommendations(comparisons, avg_effectiveness)
        }

        # Update session
        session.overall_effectiveness = avg_effectiveness
        session.end_time = time.time()

        return report

    def _analyze_session_trends(self, comparisons: List[AutoTuningComparison]) -> Dict[str, Any]:
        """Analyze performance trends within the session.

        Args:
            comparisons: List of performance comparisons

        Returns:
            Trend analysis results
        """
        if len(comparisons) < 3:
            return {'trend': 'insufficient_data', 'consistency': 'unknown'}

        # Calculate effectiveness trend
        effectiveness_scores = [c.effectiveness_score for c in comparisons]
        improvements = [c.improvement_percentage for c in comparisons]

        # Simple linear trend analysis
        early_avg = sum(effectiveness_scores[:len(effectiveness_scores)//2]) / (len(effectiveness_scores)//2)
        late_avg = sum(effectiveness_scores[len(effectiveness_scores)//2:]) / (len(effectiveness_scores) - len(effectiveness_scores)//2)

        if late_avg > early_avg * 1.1:
            trend = 'improving'
        elif late_avg < early_avg * 0.9:
            trend = 'degrading'
        else:
            trend = 'stable'

        # Consistency analysis
        effectiveness_variance = sum((s - early_avg) ** 2 for s in effectiveness_scores) / len(effectiveness_scores)
        if effectiveness_variance < 100:
            consistency = 'high'
        elif effectiveness_variance < 400:
            consistency = 'medium'
        else:
            consistency = 'low'

        return {
            'trend': trend,
            'consistency': consistency,
            'effectiveness_variance': round(effectiveness_variance, 2),
            'early_session_avg': round(early_avg, 2),
            'late_session_avg': round(late_avg, 2)
        }

    def _generate_session_recommendations(self, comparisons: List[AutoTuningComparison],
                                         avg_effectiveness: float) -> List[str]:
        """Generate session-level recommendations.

        Args:
            comparisons: List of performance comparisons
            avg_effectiveness: Average effectiveness score

        Returns:
            List of recommendations
        """
        recommendations = []

        if avg_effectiveness >= 75:
            recommendations.append("Auto-tuning is highly effective - maintain current settings")
        elif avg_effectiveness >= 50:
            recommendations.append("Auto-tuning shows moderate effectiveness - consider fine-tuning parameters")
        else:
            recommendations.append("Auto-tuning effectiveness is low - review configuration and thresholds")

        # Analysis by adjustment type
        adjustment_types = {}
        for comp in comparisons:
            adj_type = comp.adjustment_type
            if adj_type not in adjustment_types:
                adjustment_types[adj_type] = []
            adjustment_types[adj_type].append(comp.effectiveness_score)

        for adj_type, scores in adjustment_types.items():
            avg_score = sum(scores) / len(scores)
            if avg_score < 40:
                recommendations.append(f"Consider disabling {adj_type} auto-tuning - consistently low effectiveness")

        # Memory and performance specific recommendations
        memory_impacts = [c.after_snapshot.memory_usage_mb - c.before_snapshot.memory_usage_mb for c in comparisons]
        avg_memory_impact = sum(memory_impacts) / len(memory_impacts)

        if avg_memory_impact > 50:  # More than 50MB average increase
            recommendations.append("Auto-tuning is increasing memory usage significantly - review memory thresholds")

        return recommendations

    def save_session_report(self, report: Dict[str, Any] = None) -> str:
        """Save session report to file.

        Args:
            report: Report to save (generated if None)

        Returns:
            Path to saved report file
        """
        if report is None:
            report = self.generate_session_report()

        if not report:
            raise ValueError("No report available to save")

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"auto_tuning_validation_{report['session_id']}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, 'auto_tuning_validation', filename)

        # Save report
        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2)

        print_success(f"Auto-tuning validation report saved: {filepath}")
        return filepath

    def end_validation_session(self, save_report: bool = True) -> Optional[Dict[str, Any]]:
        """End current validation session and optionally save report.

        Args:
            save_report: Whether to save the session report

        Returns:
            Final session report
        """
        if not self.current_session:
            print_warning("No active validation session to end")
            return None

        report = self.generate_session_report()

        if save_report and report:
            self.save_session_report(report)

        # Archive session
        if self.current_session:
            self.validation_history.append(self.current_session)
            self.current_session = None

        print_info(f"🏁 Validation session ended: {report['total_comparisons']} comparisons, "
                  f"{report['overall_effectiveness']:.1f}% avg effectiveness")

        return report

    def get_historical_effectiveness(self, operation_type: str = None) -> Dict[str, Any]:
        """Get historical auto-tuning effectiveness across all sessions.

        Args:
            operation_type: Filter by specific operation type

        Returns:
            Historical effectiveness analysis
        """
        if not self.validation_history:
            return {'message': 'No historical validation data available'}

        all_comparisons = []
        for session in self.validation_history:
            for comp in session.comparisons:
                if operation_type is None or comp.before_snapshot.operation_type == operation_type:
                    all_comparisons.append(comp)

        if not all_comparisons:
            return {'message': f'No historical data for operation type: {operation_type}'}

        # Calculate historical metrics
        avg_effectiveness = sum(c.effectiveness_score for c in all_comparisons) / len(all_comparisons)
        avg_improvement = sum(c.improvement_percentage for c in all_comparisons) / len(all_comparisons)

        improvements = len([c for c in all_comparisons if c.effectiveness_score >= 50])
        regressions = len(all_comparisons) - improvements

        return {
            'operation_type': operation_type or 'all',
            'total_adjustments': len(all_comparisons),
            'total_sessions': len(self.validation_history),
            'average_effectiveness': round(avg_effectiveness, 2),
            'average_improvement_percentage': round(avg_improvement, 2),
            'improvement_rate': round(improvements / len(all_comparisons) * 100, 1),
            'regression_rate': round(regressions / len(all_comparisons) * 100, 1),
            'recommendation': (
                'Auto-tuning is highly effective historically' if avg_effectiveness >= 75 else
                'Auto-tuning shows moderate historical effectiveness' if avg_effectiveness >= 50 else
                'Historical auto-tuning effectiveness is low - review configuration'
            )
        }