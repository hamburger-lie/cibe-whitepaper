"""
Reflection Criteria Module
Provides functionality to evaluate reflection reports based on predefined criteria.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass


@dataclass
class EvaluationScore:
    """Data class to store evaluation scores for individual criteria."""
    criterion_name: str
    score: float  # 0.0 to 1.0
    max_score: float
    feedback: str
    details: Dict[str, Any]


@dataclass
class EvaluationResult:
    """Data class to store evaluation results for a reflection report."""
    report_id: str
    overall_score: float
    criterion_scores: List[EvaluationScore]
    strengths: List[str]
    weaknesses: List[str]
    recommendations: List[str]
    evaluated_at: datetime


class ReflectionCriteria:
    """A comprehensive reflection evaluation agent."""
    
    def __init__(self, criteria_weights: Optional[Dict[str, float]] = None, log_level: str = "INFO"):
        """
        Initialize the ReflectionCriteria evaluator.
        
        Args:
            criteria_weights: Optional weights for each evaluation criterion
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.criteria_weights = criteria_weights or self._default_criteria_weights()
        self.logger = self._setup_logger(log_level)
        
        # Define evaluation criteria
        self.criteria = {
            "clarity_coherence": {
                "name": "Clarity and Coherence",
                "description": "How clear, well-organized, and logically structured the reflection is",
                "max_score": 1.0,
                "weight": self.criteria_weights.get("clarity_coherence", 0.25)
            },
            "depth_analysis": {
                "name": "Depth of Analysis",
                "description": "The thoroughness and insightfulness of the analysis",
                "max_score": 1.0,
                "weight": self.criteria_weights.get("depth_analysis", 0.25)
            },
            "actionability": {
                "name": "Actionability",
                "description": "The extent to which insights lead to concrete actions or changes",
                "max_score": 1.0,
                "weight": self.criteria_weights.get("actionability", 0.20)
            },
            "self_awareness": {
                "name": "Self-Awareness",
                "description": "Demonstration of understanding personal biases, assumptions, and growth areas",
                "max_score": 1.0,
                "weight": self.criteria_weights.get("self_awareness", 0.20)
            },
            "structure_organization": {
                "name": "Structure and Organization",
                "description": "How well the reflection is organized with clear sections and flow",
                "max_score": 1.0,
                "weight": self.criteria_weights.get("structure_organization", 0.10)
            }
        }
        
        # Validate weights sum to 1.0
        total_weight = sum(self.criteria_weights.values())
        if not abs(total_weight - 1.0) < 0.001:
            raise ValueError(f"Criteria weights must sum to 1.0, got {total_weight}")
    
    def _setup_logger(self, log_level: str) -> logging.Logger:
        """Set up logging for the reflection criteria evaluator."""
        logger = logging.getLogger("ReflectionCriteria")
        logger.setLevel(getattr(logging, log_level.upper()))
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def _default_criteria_weights(self) -> Dict[str, float]:
        """Default weights for evaluation criteria."""
        return {
            "clarity_coherence": 0.25,
            "depth_analysis": 0.25,
            "actionability": 0.20,
            "self_awareness": 0.20,
            "structure_organization": 0.10
        }
    
    def evaluate_report(self, reflection_report: Dict[str, Any], report_id: str = "unknown") -> EvaluationResult:
        """
        Evaluate a reflection report based on predefined criteria.
        
        Args:
            reflection_report: Dictionary containing the reflection report content
            report_id: Optional identifier for the report
            
        Returns:
            EvaluationResult object containing scores and feedback
        """
        self.logger.info(f"Evaluating reflection report: {report_id}")
        
        # Extract report content
        content = reflection_report.get("content", "")
        title = reflection_report.get("title", "")
        sections = reflection_report.get("sections", {})
        
        # Evaluate each criterion
        criterion_scores = []
        strengths = []
        weaknesses = []
        recommendations = []
        
        for criterion_key, criterion_info in self.criteria.items():
            score, feedback, details = self._evaluate_criterion(
                criterion_key, criterion_info, content, sections, title
            )
            
            criterion_score = EvaluationScore(
                criterion_name=criterion_info["name"],
                score=score,
                max_score=criterion_info["max_score"],
                feedback=feedback,
                details=details
            )
            criterion_scores.append(criterion_score)
            
            # Analyze strengths and weaknesses
            if score >= 0.7:
                strengths.append(f"Strong {criterion_info['name']}: {feedback}")
            elif score < 0.4:
                weaknesses.append(f"Needs improvement in {criterion_info['name']}: {feedback}")
                recommendations.append(f"Improve {criterion_info['name']} by: {self._get_improvement_suggestion(criterion_key)}")
        
        # Calculate overall weighted score
        overall_score = sum(
            score.score * self.criteria[criterion_key]["weight"] 
            for criterion_key, score in zip(self.criteria.keys(), criterion_scores)
        )
        
        self.logger.info(f"Evaluation complete. Overall score: {overall_score:.2f}")
        
        return EvaluationResult(
            report_id=report_id,
            overall_score=overall_score,
            criterion_scores=criterion_scores,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            evaluated_at=datetime.now()
        )
    
    def _evaluate_criterion(self, criterion_key: str, criterion_info: Dict[str, Any], 
                           content: str, sections: Dict[str, Any], title: str) -> tuple:
        """
        Evaluate a specific criterion based on the reflection report.
        
        Args:
            criterion_key: The key identifying the criterion
            criterion_info: Information about the criterion
            content: The reflection content
            sections: The sections of the reflection
            title: The reflection title
            
        Returns:
            Tuple of (score, feedback, details)
        """
        if criterion_key == "clarity_coherence":
            return self._evaluate_clarity_coherence(content, title)
        elif criterion_key == "depth_analysis":
            return self._evaluate_depth_analysis(content, sections)
        elif criterion_key == "actionability":
            return self._evaluate_actionability(content, sections)
        elif criterion_key == "self_awareness":
            return self._evaluate_self_awareness(content, sections)
        elif criterion_key == "structure_organization":
            return self._evaluate_structure_organization(content, sections)
        else:
            return 0.0, "Unknown criterion", {}
    
    def _evaluate_clarity_coherence(self, content: str, title: str) -> tuple:
        """Evaluate clarity and coherence of the reflection."""
        details = {}
        
        # Check if title exists and is descriptive
        title_score = 0.0
        if title and len(title.strip()) > 5:
            title_score = min(1.0, len(title.strip()) / 20)
        details["title_score"] = title_score
        
        # Check content length (should be substantial enough for clarity)
        content_length_score = min(1.0, len(content) / 500)  # Normalize to 500 chars
        details["content_length_score"] = content_length_score
        
        # Check for basic coherence indicators
        sentence_count = len([s for s in content.split('.') if s.strip()])
        avg_sentence_length = len(content) / max(1, sentence_count)
        
        # Ideal sentence length is 15-25 words
        sentence_length_score = 1.0 if 15 <= avg_sentence_length <= 25 else 0.7
        details["sentence_length_score"] = sentence_length_score
        
        # Check for logical flow indicators
        transition_words = ["however", "therefore", "furthermore", "additionally", "consequently", "thus", "moreover"]
        transition_count = sum(1 for word in transition_words if word in content.lower())
        transition_score = min(1.0, transition_count / 3)
        details["transition_score"] = transition_score
        
        # Overall clarity score
        overall_score = (title_score + content_length_score + sentence_length_score + transition_score) / 4
        
        feedback = f"Reflection {'has good' if overall_score >= 0.7 else 'needs improvement in'} clarity and coherence"
        if overall_score < 0.5:
            feedback += ". Consider adding more descriptive language and improving sentence structure."
        
        return overall_score, feedback, details
    
    def _evaluate_depth_analysis(self, content: str, sections: Dict[str, Any]) -> tuple:
        """Evaluate depth of analysis in the reflection."""
        details = {}
        
        # Check for analytical language
        analytical_indicators = ["analyze", "examine", "explore", "investigate", "consider", "evaluate", "assess"]
        analytical_count = sum(1 for indicator in analytical_indicators if indicator in content.lower())
        analytical_score = min(1.0, analytical_count / 3)
        details["analytical_score"] = analytical_score
        
        # Check for specific examples or evidence
        example_indicators = ["for example", "such as", "specifically", "instance", "case"]
        example_count = sum(1 for indicator in example_indicators if indicator in content.lower())
        example_score = min(1.0, example_count / 2)
        details["example_score"] = example_score
        
        # Check for multiple perspectives
        perspective_indicators = ["however", "on the other hand", "alternatively", "different perspective", "contrast"]
        perspective_count = sum(1 for indicator in perspective_indicators if indicator in content.lower())
        perspective_score = min(1.0, perspective_count / 2)
        details["perspective_score"] = perspective_score
        
        # Check for causal language
        causal_indicators = ["because", "therefore", "as a result", "consequently", "due to", "caused by"]
        causal_count = sum(1 for indicator in causal_indicators if indicator in content.lower())
        causal_score = min(1.0, causal_count / 2)
        details["causal_score"] = causal_score
        
        overall_score = (analytical_score + example_score + perspective_score + causal_score) / 4
        
        feedback = f"Analysis depth is {'good' if overall_score >= 0.7 else 'limited'}"
        if overall_score < 0.5:
            feedback += ". Consider providing more specific examples and exploring multiple perspectives."
        
        return overall_score, feedback, details
    
    def _evaluate_actionability(self, content: str, sections: Dict[str, Any]) -> tuple:
        """Evaluate actionability of the reflection."""
        details = {}
        
        # Check for action-oriented language
        action_words = ["will", "plan to", "intend to", "commit to", "aim to", "goal", "objective"]
        action_count = sum(1 for word in action_words if word in content.lower())
        action_score = min(1.0, action_count / 3)
        details["action_score"] = action_score
        
        # Check for specific next steps
        step_indicators = ["next step", "first step", "subsequently", "then", "following", "after"]
        step_count = sum(1 for indicator in step_indicators if indicator in content.lower())
        step_score = min(1.0, step_count / 2)
        details["step_score"] = step_score
        
        # Check for measurable outcomes
        measurable_indicators = ["measure", "track", "monitor", "assess", "evaluate", "review"]
        measurable_count = sum(1 for indicator in measurable_indicators if indicator in content.lower())
        measurable_score = min(1.0, measurable_count / 2)
        details["measurable_score"] = measurable_score
        
        # Check for timeline indicators
        time_indicators = ["next week", "within", "by", "during", "when", "schedule"]
        time_count = sum(1 for indicator in time_indicators if indicator in content.lower())
        time_score = min(1.0, time_count / 2)
        details["time_score"] = time_score
        
        overall_score = (action_score + step_score + measurable_score + time_score) / 4
        
        feedback = f"Actionability is {'strong' if overall_score >= 0.7 else 'weak'}"
        if overall_score < 0.5:
            feedback += ". Consider adding specific action items and measurable outcomes."
        
        return overall_score, feedback, details
    
    def _evaluate_self_awareness(self, content: str, sections: Dict[str, Any]) -> tuple:
        """Evaluate self-awareness demonstrated in the reflection."""
        details = {}
        
        # Check for self-reflection language
        self_reflection_words = ["I realize", "I recognize", "I understand", "I acknowledge", "I see now"]
        self_reflection_count = sum(1 for word in self_reflection_words if word in content.lower())
        self_reflection_score = min(1.0, self_reflection_count / 2)
        details["self_reflection_score"] = self_reflection_score
        
        # Check for admission of limitations or mistakes
        limitation_indicators = "I made a mistake" in content.lower() or "I was wrong" in content.lower() or "I need to improve" in content.lower()
        limitation_score = 1.0 if limitation_indicators else 0.0
        details["limitation_score"] = limitation_score
        
        # Check for growth mindset language
        growth_indicators = ["learned", "grew", "developed", "improved", "progress", "growth"]
        growth_count = sum(1 for indicator in growth_indicators if indicator in content.lower())
        growth_score = min(1.0, growth_count / 3)
        details["growth_score"] = growth_score
        
        # Check for emotional awareness
        emotion_indicators = ["felt", "felt that", "emotion", "frustrated", "challenged", "satisfied"]
        emotion_count = sum(1 for indicator in emotion_indicators if indicator in content.lower())
        emotion_score = min(1.0, emotion_count / 2)
        details["emotion_score"] = emotion_score
        
        overall_score = (self_reflection_score + limitation_score + growth_score + emotion_score) / 4
        
        feedback = f"Self-awareness is {'well-developed' if overall_score >= 0.7 else 'limited'}"
        if overall_score < 0.5:
            feedback += ". Consider acknowledging personal limitations and expressing emotional responses."
        
        return overall_score, feedback, details
    
    def _evaluate_structure_organization(self, content: str, sections: Dict[str, Any]) -> tuple:
        """Evaluate structure and organization of the reflection."""
        details = {}
        
        # Check for paragraph structure
        paragraph_count = len([p for p in content.split('\n\n') if p.strip()])
        paragraph_score = min(1.0, paragraph_count / 5)  # Normalize to 5 paragraphs
        details["paragraph_score"] = paragraph_score
        
        # Check for section headers
        section_headers = ["introduction", "analysis", "conclusion", "reflection", "summary", "key insights"]
        header_count = sum(1 for header in section_headers if header in content.lower())
        header_score = min(1.0, header_count / 3)
        details["header_score"] = header_score
        
        # Check for logical flow between paragraphs
        transition_paragraphs = ["however", "furthermore", "additionally", "consequently", "therefore"]
        transition_count = sum(1 for transition in transition_paragraphs if transition in content.lower())
        transition_score = min(1.0, transition_count / 2)
        details["transition_score"] = transition_score
        
        # Check for conclusion
        conclusion_indicators = ["in conclusion", "to summarize", "final thoughts", "takeaway", "key takeaway"]
        conclusion_score = 1.0 if any(indicator in content.lower() for indicator in conclusion_indicators) else 0.0
        details["conclusion_score"] = conclusion_score
        
        overall_score = (paragraph_score + header_score + transition_score + conclusion_score) / 4
        
        feedback = f"Structure and organization is {'excellent' if overall_score >= 0.7 else 'needs improvement'}"
        if overall_score < 0.5:
            feedback += ". Consider adding clear sections and improving paragraph structure."
        
        return overall_score, feedback, details
    
    def _get_improvement_suggestion(self, criterion_key: str) -> str:
        """Get improvement suggestions for a specific criterion."""
        suggestions = {
            "clarity_coherence": "Use clear, concise language and ensure logical flow between ideas.",
            "depth_analysis": "Provide specific examples and explore multiple perspectives.",
            "actionability": "Add concrete action items with timelines and measurable outcomes.",
            "self_awareness": "Acknowledge personal limitations and express emotional responses.",
            "structure_organization": "Use clear section headers and ensure proper paragraph structure."
        }
        return suggestions.get(criterion_key, "Work on improving this criterion.")
    
    def export_evaluation(self, evaluation_result: EvaluationResult, format: str = "json", filepath: Optional[str] = None) -> str:
        """
        Export evaluation results to specified format.
        
        Args:
            evaluation_result: EvaluationResult to export
            format: Export format (json, txt)
            filepath: Optional file path to save the evaluation
            
        Returns:
            Exported evaluation as string
        """
        if format.lower() == "json":
            evaluation_str = json.dumps(evaluation_result, default=self._serialize_datetime, indent=2)
        elif format.lower() == "txt":
            evaluation_str = self._export_to_txt(evaluation_result)
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        if filepath:
            with open(filepath, 'w') as f:
                f.write(evaluation_str)
            self.logger.info(f"Evaluation exported to {filepath}")
        
        return evaluation_str
    
    def _serialize_datetime(self, obj) -> str:
        """Custom JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _export_to_txt(self, evaluation_result: EvaluationResult) -> str:
        """Export evaluation to text format."""
        lines = []
        lines.append("=" * 60)
        lines.append("REFLECTION EVALUATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Report ID: {evaluation_result.report_id}")
        lines.append(f"Evaluated: {evaluation_result.evaluated_at}")
        lines.append(f"Overall Score: {evaluation_result.overall_score:.2f}")
        lines.append("")
        
        # Criterion scores
        lines.append("EVALUATION CRITERIA")
        lines.append("-" * 30)
        for score in evaluation_result.criterion_scores:
            lines.append(f"{score.criterion_name}: {score.score:.2f}/1.0")
            lines.append(f"  Feedback: {score.feedback}")
            lines.append("")
        
        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 30)
        lines.append(f"Total Criteria Evaluated: {len(evaluation_result.criterion_scores)}")
        lines.append("")
        
        # Strengths
        if evaluation_result.strengths:
            lines.append("STRENGTHS")
            lines.append("-" * 30)
            for strength in evaluation_result.strengths:
                lines.append(f"• {strength}")
            lines.append("")
        
        # Weaknesses
        if evaluation_result.weaknesses:
            lines.append("AREAS FOR IMPROVEMENT")
            lines.append("-" * 30)
            for weakness in evaluation_result.weaknesses:
                lines.append(f"• {weakness}")
            lines.append("")
        
        # Recommendations
        if evaluation_result.recommendations:
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 30)
            for recommendation in evaluation_result.recommendations:
                lines.append(f"• {recommendation}")
            lines.append("")
        
        return "\n".join(lines)