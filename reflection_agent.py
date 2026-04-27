"""
Reflection Agent Module
Provides a comprehensive reflection agent that coordinates evaluation and storage functionality.
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

from reflection_criteria import ReflectionCriteria, EvaluationResult
from reflection_storage import DEFAULT_REFLECTION_STORAGE_PATH, ReflectionStorage


TRUSTED_SOURCE_DOMAINS = (
    "loreal-finance.com",
    "loreal.com",
    "kpmg.com",
    "circana.com",
    "mckinsey.com",
    "deloitte.com",
    "pwc.com",
    "ey.com",
    "reuters.com",
    "bloomberg.com",
    "wwd.com",
    "voguebusiness.com",
    "businessoffashion.com",
    "jingdaily.com",
)


@dataclass
class ReflectionSession:
    """Data class to store reflection session information."""
    session_id: str
    query: str
    response: str
    reflection: str
    reflection_mode: str = "user"
    evaluation_result: Optional[EvaluationResult] = None
    created_at: datetime = None
    updated_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


class ReflectionAgent:
    """
    A comprehensive reflection agent that coordinates evaluation, storage, and prompt improvement.
    
    This agent integrates reflection criteria evaluation with storage functionality
    to provide a complete reflection system.
    """
    
    def __init__(self, 
                 storage_path: str = DEFAULT_REFLECTION_STORAGE_PATH,
                 criteria_weights: Optional[Dict[str, float]] = None,
                 log_level: str = "INFO"):
        """
        Initialize the ReflectionAgent.
        
        Args:
            storage_path: Path to the JSON file for storing reflections
            criteria_weights: Optional weights for evaluation criteria
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.storage = ReflectionStorage(storage_path)
        self.evaluator = ReflectionCriteria(criteria_weights, log_level)
        self.logger = self._setup_logger(log_level)
        
    def _setup_logger(self, log_level: str) -> logging.Logger:
        """Set up logging for the reflection agent."""
        logger = logging.getLogger("ReflectionAgent")
        logger.setLevel(getattr(logging, log_level.upper()))
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def evaluate_and_reflect(self, 
                           query: str, 
                           response: str, 
                           reflection: str,
                           session_id: Optional[str] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> ReflectionSession:
        """
        Evaluate a reflection and create a reflection session.
        
        Args:
            query: The original query that prompted the response
            response: The response to the query
            reflection: The user's reflection on their response
            session_id: Optional session identifier
            metadata: Optional metadata to store with the reflection
            
        Returns:
            ReflectionSession object containing the evaluation results
        """
        self.logger.info(f"Starting reflection evaluation for session: {session_id or 'auto-generated'}")

        reflection_mode = "user"
        if not reflection or not reflection.strip():
            if self._has_reference_section(response):
                reflection = self._generate_source_consistency_reflection(query, response)
                reflection_mode = "source_consistency"
            else:
                reflection = self._generate_system_reflection(query, response)
                reflection_mode = "auto_generated"
        
        # Create reflection report structure for evaluation
        reflection_report = {
            "content": reflection,
            "title": f"Reflection on: {query[:50]}..." if len(query) > 50 else f"Reflection on: {query}",
            "sections": self._extract_sections(reflection),
            "query": query,
            "response": response
        }
        
        # Evaluate the reflection
        evaluation_result = self.evaluator.evaluate_report(
            reflection_report, 
            report_id=session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        # Create reflection session
        if not session_id:
            session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
        session = ReflectionSession(
            session_id=session_id,
            query=query,
            response=response,
            reflection=reflection,
            reflection_mode=reflection_mode,
            evaluation_result=evaluation_result,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Store the reflection
        storage_metadata = {
            "session_id": session_id,
            "query": query,
            "response": response,
            "reflection_mode": reflection_mode,
            "evaluation": self._serialize_evaluation(evaluation_result),
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat()
        }
        
        success = self.storage.save_reflection(reflection, storage_metadata)
        if success:
            self.logger.info(f"Reflection session {session_id} saved successfully")
        else:
            self.logger.error(f"Failed to save reflection session {session_id}")
        
        return session

    def _has_reference_section(self, response: str) -> bool:
        response_lower = (response or "").lower()
        return (
            "参考资料与链接" in response
            or "参考资料" in response
            or "references" in response_lower
        ) and bool(re.search(r"https?://", response or ""))

    def _extract_reference_items(self, response: str) -> List[Dict[str, str]]:
        items = []
        for match in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", response or ""):
            title = match.group(1).strip()
            url = match.group(2).strip()
            domain_match = re.search(r"https?://(?:www\.)?([^/\s)]+)", url)
            domain = domain_match.group(1).lower() if domain_match else ""
            items.append({"title": title, "url": url, "domain": domain})
        return items

    def _generate_source_consistency_reflection(self, query: str, response: str) -> str:
        """Generate a report reflection focused on source consistency."""
        references = self._extract_reference_items(response)
        trusted_refs = [
            ref for ref in references
            if any(domain in ref["domain"] for domain in TRUSTED_SOURCE_DOMAINS)
        ]
        untrusted_refs = [
            ref for ref in references
            if ref not in trusted_refs
        ]

        body = response.split("## 参考资料", 1)[0]
        body_sentences = [
            sentence.strip()
            for sentence in re.split(r"[。！？!?\n]+", body)
            if len(sentence.strip()) >= 18
        ]
        evidence_terms = ("报告", "财报", "机构", "公开", "数据", "增长", "市场", "消费者", "高端", "渠道")
        evidence_aligned_sentences = [
            sentence for sentence in body_sentences
            if any(term in sentence for term in evidence_terms)
        ]

        coverage_ratio = (
            min(1.0, len(trusted_refs) / max(1, min(4, len(references))))
            if references else 0.0
        )
        alignment_ratio = (
            min(1.0, len(evidence_aligned_sentences) / max(1, len(body_sentences)))
            if body_sentences else 0.0
        )

        trusted_domains = sorted({ref["domain"] for ref in trusted_refs})
        untrusted_domains = sorted({ref["domain"] for ref in untrusted_refs})

        if trusted_refs:
            source_summary = (
                f"I found {len(trusted_refs)} trusted reference links from "
                f"{', '.join(trusted_domains)}."
            )
        else:
            source_summary = "I found no trusted reference links in the report."

        if untrusted_domains:
            risk_summary = (
                f"I also found lower-confidence sources that require review: "
                f"{', '.join(untrusted_domains)}."
            )
        else:
            risk_summary = "I found no obvious low-confidence source domains in the reference section."

        return (
            "Introduction\n"
            f"I recognize that this is a source consistency reflection for the report query: {query}.\n\n"
            "Source Consistency Analysis\n"
            f"I analyze the report against its reference section. {source_summary} "
            f"The source coverage score is approximately {coverage_ratio:.2f}, based on trusted official, institutional, or authoritative domains. "
            f"The evidence alignment score is approximately {alignment_ratio:.2f}, based on whether substantive body claims use market, data, institution, or public-report language.\n\n"
            "Reference Quality Reflection\n"
            f"I understand that source quality matters more than source count. {risk_summary} "
            "I acknowledge that the report should avoid adding claims that are not traceable to the listed sources, especially precise percentages, market-size numbers, and brand performance comparisons.\n\n"
            "Actionability\n"
            "I plan to improve the next version by keeping the strongest trusted references, removing weak or unrelated sources, and ensuring each major market judgement can be traced to at least one listed source. "
            "The next step is to review unsupported numeric claims and either attach a source-backed explanation or soften the wording.\n\n"
            "Conclusion\n"
            "In conclusion, the report passes source consistency when trusted reference links are present, the reference section is relevant to the body, and unsupported precise claims are minimized."
        )

    def _generate_system_reflection(self, query: str, response: str) -> str:
        """Generate a structured fallback reflection for report-like responses."""
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        headings = [line for line in lines if line.startswith("#")]
        bullet_count = sum(1 for line in lines if line.startswith(("-", "*")))
        has_summary = any("执行摘要" in line or "summary" in line.lower() for line in lines)
        has_conclusion = any("结论" in line or "建议" in line or "conclusion" in line.lower() for line in lines)
        has_references = any("参考" in line or "资料" in line or "reference" in line.lower() for line in lines)
        approx_sections = max(1, len(headings))

        strengths = []
        if has_summary:
            strengths.append("the report includes an executive summary to clarify the main judgement")
        if has_conclusion:
            strengths.append("the report includes conclusion or action-oriented recommendations")
        if approx_sections >= 3:
            strengths.append("the structure is organized into multiple sections with a clearer flow")
        if not strengths:
            strengths.append("the response addresses the requested topic directly")

        improvements = []
        if not has_references:
            improvements.append("I need to improve source traceability by adding clearer references and links")
        if bullet_count < 2:
            improvements.append("I need to improve actionability with more concrete next steps and measurable actions")
        if approx_sections < 3:
            improvements.append("I need to improve structure with clearer sectioning and transitions")
        if not improvements:
            improvements.append("I plan to keep strengthening evidence quality and source alignment in the next revision")

        return (
            "Introduction\n"
            f"I recognize that this response is a report-style answer to the query: {query}.\n\n"
            "Analysis\n"
            f"I analyze that the current draft contains approximately {approx_sections} major sections and {bullet_count} actionable bullets. "
            f"It includes {', '.join(strengths)}. However, I also see that {improvements[0]}.\n\n"
            "Reflection\n"
            "I realize the report should balance clarity, evidence, actionability, and structure. "
            f"I understand that the strongest areas are {', '.join(strengths[:2])}. "
            f"I acknowledge that {', '.join(improvements)}.\n\n"
            "Conclusion\n"
            "In conclusion, I plan to improve the next version by strengthening structure, evidence, and actionable guidance. "
            "The next step is to keep the report coherent, use clearer transitions, and preserve measurable recommendations."
        )
    
    def generate_improved_prompt(self, 
                               query: str, 
                               response: str, 
                               reflection: str,
                               improvement_focus: Optional[List[str]] = None,
                               max_length: int = 500) -> str:
        """
        Generate an improved prompt based on reflection evaluation.
        
        Args:
            query: The original query
            response: The original response
            reflection: The user's reflection on their response
            improvement_focus: Optional list of criteria to focus on for improvement
            max_length: Maximum length of the improved prompt
            
        Returns:
            Improved prompt string
        """
        self.logger.info("Generating improved prompt based on reflection")
        
        # First evaluate the reflection to understand areas for improvement
        reflection_report = {
            "content": reflection,
            "title": f"Reflection on: {query[:50]}..." if len(query) > 50 else f"Reflection on: {query}",
            "sections": self._extract_sections(reflection),
            "query": query,
            "response": response
        }
        
        evaluation_result = self.evaluator.evaluate_report(
            reflection_report, 
            report_id="prompt_improvement"
        )
        
        # Determine improvement focus
        if improvement_focus is None:
            # Use evaluation results to determine focus areas
            improvement_focus = []
            for score in evaluation_result.criterion_scores:
                if score.score < 0.7:  # Areas that need improvement
                    improvement_focus.append(score.criterion_name.lower().replace(" ", "_"))
        
        # Generate improved prompt based on focus areas
        improved_prompt = self._build_improved_prompt(
            query, response, reflection, evaluation_result, improvement_focus, max_length
        )
        
        self.logger.info(f"Generated improved prompt focusing on: {improvement_focus}")
        return improved_prompt
    
    def _extract_sections(self, reflection: str) -> Dict[str, Any]:
        """Extract sections from reflection content."""
        sections = {}
        
        # Simple section extraction based on common patterns
        lines = reflection.split('\n')
        current_section = "general"
        section_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Check for section headers
            if line.lower().startswith(('introduction', 'analysis', 'reflection', 'conclusion', 'summary')):
                if current_section != "general" and section_content:
                    sections[current_section] = ' '.join(section_content)
                current_section = line.lower().split()[0]
                section_content = [line]
            else:
                section_content.append(line)
        
        # Add the last section
        if section_content:
            sections[current_section] = ' '.join(section_content)
        
        return sections
    
    def _serialize_evaluation(self, evaluation_result: EvaluationResult) -> Dict[str, Any]:
        """Serialize evaluation result for storage."""
        return {
            "overall_score": evaluation_result.overall_score,
            "evaluated_at": evaluation_result.evaluated_at.isoformat(),
            "criterion_scores": [
                {
                    "criterion_name": score.criterion_name,
                    "score": score.score,
                    "max_score": score.max_score,
                    "feedback": score.feedback,
                    "details": score.details
                }
                for score in evaluation_result.criterion_scores
            ],
            "strengths": evaluation_result.strengths,
            "weaknesses": evaluation_result.weaknesses,
            "recommendations": evaluation_result.recommendations
        }
    
    def _build_improved_prompt(self, 
                            query: str, 
                            response: str, 
                            reflection: str,
                            evaluation_result: EvaluationResult,
                            improvement_focus: List[str],
                            max_length: int) -> str:
        """Build improved prompt based on evaluation results and focus areas."""
        
        # Start with the original query
        improved_prompt = f"Original Query: {query}\n\n"
        
        # Add reflection insights
        improved_prompt += f"Previous Reflection Insights:\n{reflection}\n\n"
        
        # Add evaluation feedback
        improved_prompt += "Evaluation Feedback:\n"
        for score in evaluation_result.criterion_scores:
            if score.score < 0.7 or score.criterion_name.lower().replace(" ", "_") in improvement_focus:
                improved_prompt += f"- {score.criterion_name}: {score.feedback}\n"
        
        # Add specific recommendations
        if evaluation_result.recommendations:
            improved_prompt += "\nRecommendations for Improvement:\n"
            for rec in evaluation_result.recommendations:
                improved_prompt += f"- {rec}\n"
        
        # Add improvement instructions based on focus areas
        improved_prompt += "\nFor this improved response, please focus on:\n"
        
        focus_mapping = {
            "clarity_coherence": "Providing clear, well-organized explanations with logical flow",
            "depth_analysis": "Including deeper analysis, specific examples, and multiple perspectives",
            "actionability": "Suggesting concrete actions, steps, and measurable outcomes",
            "self_awareness": "Demonstrating understanding of personal biases and growth areas",
            "structure_organization": "Using clear sections and proper paragraph organization"
        }
        
        for focus in improvement_focus:
            if focus in focus_mapping:
                improved_prompt += f"- {focus_mapping[focus]}\n"
        
        # Truncate if necessary
        if len(improved_prompt) > max_length:
            improved_prompt = improved_prompt[:max_length-3] + "..."
        
        return improved_prompt
    
    def get_reflection_sessions(self, 
                              limit: Optional[int] = None,
                              start_date: Optional[str] = None,
                              end_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get stored reflection sessions.
        
        Args:
            limit: Maximum number of sessions to return
            start_date: Filter sessions from this date
            end_date: Filter sessions up to this date
            
        Returns:
            List of reflection session dictionaries
        """
        return self.storage.get_reflections(limit, start_date, end_date)
    
    def get_reflection_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific reflection session by ID.
        
        Args:
            session_id: The session ID to retrieve
            
        Returns:
            Reflection session dictionary or None if not found
        """
        reflections = self.storage.get_reflections()
        for reflection in reflections:
            metadata = reflection.get('metadata', {})
            if metadata.get('session_id') == session_id:
                return {
                    'session_id': session_id,
                    'query': metadata.get('query', ''),
                    'response': metadata.get('response', ''),
                    'reflection': reflection.get('text', ''),
                    'reflection_mode': metadata.get('reflection_mode', 'user'),
                    'evaluation': metadata.get('evaluation', {}),
                    'created_at': metadata.get('created_at', ''),
                    'updated_at': metadata.get('updated_at', ''),
                    'timestamp': reflection.get('timestamp', '')
                }
        return None
    
    def export_session_evaluation(self, session_id: str, format: str = "json") -> Optional[str]:
        """
        Export evaluation results for a specific session.
        
        Args:
            session_id: The session ID to export
            format: Export format (json, txt)
            
        Returns:
            Exported evaluation as string or None if session not found
        """
        session_data = self.get_reflection_session(session_id)
        if not session_data:
            return None
            
        try:
            evaluation_data = session_data.get('evaluation', {})
            if format.lower() == "json":
                return json.dumps(evaluation_data, indent=2)
            elif format.lower() == "txt":
                return self._export_evaluation_to_txt(evaluation_data)
            else:
                raise ValueError(f"Unsupported export format: {format}")
        except Exception as e:
            self.logger.error(f"Error exporting evaluation: {e}")
            return None
    
    def _export_evaluation_to_txt(self, evaluation_data: Dict[str, Any]) -> str:
        """Export evaluation to text format."""
        lines = []
        lines.append("=" * 60)
        lines.append("REFLECTION EVALUATION EXPORT")
        lines.append("=" * 60)
        lines.append(f"Overall Score: {evaluation_data.get('overall_score', 'N/A')}")
        lines.append(f"Evaluated: {evaluation_data.get('evaluated_at', 'N/A')}")
        lines.append("")
        
        # Criterion scores
        lines.append("CRITERION SCORES")
        lines.append("-" * 30)
        for score in evaluation_data.get('criterion_scores', []):
            lines.append(f"{score.get('criterion_name', 'Unknown')}: {score.get('score', 0):.2f}/{score.get('max_score', 1)}")
            lines.append(f"  Feedback: {score.get('feedback', 'N/A')}")
            lines.append("")
        
        # Strengths
        strengths = evaluation_data.get('strengths', [])
        if strengths:
            lines.append("STRENGTHS")
            lines.append("-" * 30)
            for strength in strengths:
                lines.append(f"• {strength}")
            lines.append("")
        
        # Weaknesses
        weaknesses = evaluation_data.get('weaknesses', [])
        if weaknesses:
            lines.append("AREAS FOR IMPROVEMENT")
            lines.append("-" * 30)
            for weakness in weaknesses:
                lines.append(f"• {weakness}")
            lines.append("")
        
        # Recommendations
        recommendations = evaluation_data.get('recommendations', [])
        if recommendations:
            lines.append("RECOMMENDATIONS")
            lines.append("-" * 30)
            for recommendation in recommendations:
                lines.append(f"• {recommendation}")
            lines.append("")
        
        return "\n".join(lines)
