"""
Data Verification Module
Provides functionality to verify data points and generate verification reports.
"""

import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass


@dataclass
class VerificationResult:
    """Data class to store verification results."""
    data_point: Any
    is_valid: bool
    validation_rules: List[str]
    errors: List[str]
    warnings: List[str]
    timestamp: datetime


@dataclass
class VerificationReport:
    """Data class to store verification reports."""
    total_points: int
    valid_points: int
    invalid_points: int
    validation_rate: float
    results: List[VerificationResult]
    generated_at: datetime
    summary: Dict[str, Any]


class DataVerificationAgent:
    """A comprehensive data verification agent."""
    
    def __init__(self, validation_rules: Optional[List[str]] = None, log_level: str = "INFO"):
        """
        Initialize the DataVerificationAgent.
        
        Args:
            validation_rules: List of validation rules to apply
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.validation_rules = validation_rules or self._default_validation_rules()
        self.logger = self._setup_logger(log_level)
        
    def _setup_logger(self, log_level: str) -> logging.Logger:
        """Set up logging for the verification agent."""
        logger = logging.getLogger("DataVerificationAgent")
        logger.setLevel(getattr(logging, log_level.upper()))
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            
        return logger
    
    def _default_validation_rules(self) -> List[str]:
        """Default validation rules for data verification."""
        return [
            "not_null",
            "not_empty",
            "type_check",
            "range_check",
            "format_check"
        ]
    
    def verify_data_points(self, data_points: List[Any], 
                         custom_rules: Optional[List[str]] = None,
                         rule_parameters: Optional[Dict[str, Any]] = None) -> List[VerificationResult]:
        """
        Verify a list of data points against validation rules.
        
        Args:
            data_points: List of data points to verify
            custom_rules: Optional custom validation rules to apply
            rule_parameters: Optional parameters for validation rules
            
        Returns:
            List of VerificationResult objects
        """
        rules_to_apply = custom_rules or self.validation_rules
        parameters = rule_parameters or {}
        
        results = []
        
        for i, data_point in enumerate(data_points):
            self.logger.debug(f"Verifying data point {i+1}/{len(data_points)}")
            
            verification_result = VerificationResult(
                data_point=data_point,
                is_valid=True,
                validation_rules=rules_to_apply,
                errors=[],
                warnings=[],
                timestamp=datetime.now()
            )
            
            # Apply each validation rule
            for rule in rules_to_apply:
                try:
                    if rule == "not_null":
                        self._validate_not_null(data_point, verification_result)
                    elif rule == "not_empty":
                        self._validate_not_empty(data_point, verification_result)
                    elif rule == "type_check":
                        self._validate_type(data_point, verification_result, parameters.get("expected_types"))
                    elif rule == "range_check":
                        self._validate_range(data_point, verification_result, parameters.get("min_value"), parameters.get("max_value"))
                    elif rule == "format_check":
                        self._validate_format(data_point, verification_result, parameters.get("expected_format"))
                    else:
                        self.logger.warning(f"Unknown validation rule: {rule}")
                        verification_result.warnings.append(f"Unknown rule: {rule}")
                        
                except Exception as e:
                    error_msg = f"Error applying rule '{rule}': {str(e)}"
                    verification_result.errors.append(error_msg)
                    verification_result.is_valid = False
                    self.logger.error(error_msg)
            
            results.append(verification_result)
        
        self.logger.info(f"Verified {len(data_points)} data points")
        return results
    
    def _validate_not_null(self, data_point: Any, result: VerificationResult) -> None:
        """Validate that data point is not None."""
        if data_point is None:
            result.errors.append("Data point is None")
            result.is_valid = False
    
    def _validate_not_empty(self, data_point: Any, result: VerificationResult) -> None:
        """Validate that data point is not empty."""
        if hasattr(data_point, '__len__') and len(data_point) == 0:
            result.errors.append("Data point is empty")
            result.is_valid = False
        elif isinstance(data_point, str) and data_point.strip() == "":
            result.errors.append("Data point is empty string")
            result.is_valid = False
    
    def _validate_type(self, data_point: Any, result: VerificationResult, expected_types: Optional[List[type]] = None) -> None:
        """Validate that data point matches expected types."""
        if expected_types is None:
            return
            
        if not any(isinstance(data_point, expected_type) for expected_type in expected_types):
            result.errors.append(f"Data point type {type(data_point)} not in expected types {expected_types}")
            result.is_valid = False
    
    def _validate_range(self, data_point: Any, result: VerificationResult, min_value: Optional[Union[int, float]] = None, 
                       max_value: Optional[Union[int, float]] = None) -> None:
        """Validate that data point is within specified range."""
        if min_value is None and max_value is None:
            return
            
        try:
            numeric_value = float(data_point)
            
            if min_value is not None and numeric_value < min_value:
                result.errors.append(f"Value {numeric_value} is below minimum {min_value}")
                result.is_valid = False
                
            if max_value is not None and numeric_value > max_value:
                result.errors.append(f"Value {numeric_value} is above maximum {max_value}")
                result.is_valid = False
                
        except (ValueError, TypeError):
            result.errors.append("Data point is not numeric for range validation")
            result.is_valid = False
    
    def _validate_format(self, data_point: Any, result: VerificationResult, expected_format: Optional[str] = None) -> None:
        """Validate that data point matches expected format."""
        if expected_format is None:
            return
            
        if expected_format == "email":
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, str(data_point)):
                result.errors.append("Data point is not a valid email format")
                result.is_valid = False
                
        elif expected_format == "url":
            import re
            url_pattern = r'^https?://[^\s/$.?#].[^\s]*$'
            if not re.match(url_pattern, str(data_point)):
                result.errors.append("Data point is not a valid URL format")
                result.is_valid = False
                
        elif expected_format == "date":
            try:
                datetime.strptime(str(data_point), '%Y-%m-%d')
            except ValueError:
                result.errors.append("Data point is not a valid date format (YYYY-MM-DD)")
                result.is_valid = False
    
    def generate_verification_report(self, verification_results: List[VerificationResult]) -> VerificationReport:
        """
        Generate a comprehensive verification report from verification results.
        
        Args:
            verification_results: List of VerificationResult objects
            
        Returns:
            VerificationReport object
        """
        if not verification_results:
            self.logger.warning("No verification results provided for report generation")
            return VerificationReport(
                total_points=0,
                valid_points=0,
                invalid_points=0,
                validation_rate=0.0,
                results=[],
                generated_at=datetime.now(),
                summary={}
            )
        
        total_points = len(verification_results)
        valid_points = sum(1 for result in verification_results if result.is_valid)
        invalid_points = total_points - valid_points
        validation_rate = valid_points / total_points if total_points > 0 else 0.0
        
        # Generate summary statistics
        summary = self._generate_summary(verification_results)
        
        report = VerificationReport(
            total_points=total_points,
            valid_points=valid_points,
            invalid_points=invalid_points,
            validation_rate=validation_rate,
            results=verification_results,
            generated_at=datetime.now(),
            summary=summary
        )
        
        self.logger.info(f"Generated verification report: {valid_points}/{total_points} points valid ({validation_rate:.2%})")
        return report
    
    def _generate_summary(self, verification_results: List[VerificationResult]) -> Dict[str, Any]:
        """Generate summary statistics from verification results."""
        summary = {
            "errors_by_rule": {},
            "warnings_by_rule": {},
            "error_patterns": {},
            "validation_rules_used": list(set().union(*[result.validation_rules for result in verification_results])),
            "total_errors": sum(len(result.errors) for result in verification_results),
            "total_warnings": sum(len(result.warnings) for result in verification_results)
        }
        
        # Count errors by rule
        for result in verification_results:
            for error in result.errors:
                for rule in result.validation_rules:
                    if rule not in summary["errors_by_rule"]:
                        summary["errors_by_rule"][rule] = 0
                    summary["errors_by_rule"][rule] += 1
        
        # Count warnings by rule
        for result in verification_results:
            for warning in result.warnings:
                for rule in result.validation_rules:
                    if rule not in summary["warnings_by_rule"]:
                        summary["warnings_by_rule"][rule] = 0
                    summary["warnings_by_rule"][rule] += 1
        
        return summary
    
    def export_report(self, report: VerificationReport, format: str = "json", filepath: Optional[str] = None) -> str:
        """
        Export verification report to specified format.
        
        Args:
            report: VerificationReport to export
            format: Export format (json, csv, txt)
            filepath: Optional file path to save the report
            
        Returns:
            Exported report as string
        """
        if format.lower() == "json":
            report_str = json.dumps(report, default=self._serialize_datetime, indent=2)
        elif format.lower() == "csv":
            report_str = self._export_to_csv(report)
        elif format.lower() == "txt":
            report_str = self._export_to_txt(report)
        else:
            raise ValueError(f"Unsupported export format: {format}")
        
        if filepath:
            with open(filepath, 'w') as f:
                f.write(report_str)
            self.logger.info(f"Report exported to {filepath}")
        
        return report_str
    
    def _serialize_datetime(self, obj) -> str:
        """Custom JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def _export_to_csv(self, report: VerificationReport) -> str:
        """Export report to CSV format."""
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["Data Point", "Is Valid", "Validation Rules", "Errors", "Warnings", "Timestamp"])
        
        # Write data
        for result in report.results:
            writer.writerow([
                str(result.data_point),
                result.is_valid,
                ";".join(result.validation_rules),
                ";".join(result.errors),
                ";".join(result.warnings),
                result.timestamp.isoformat()
            ])
        
        return output.getvalue()
    
    def _export_to_txt(self, report: VerificationReport) -> str:
        """Export report to text format."""
        lines = []
        lines.append("=" * 60)
        lines.append("DATA VERIFICATION REPORT")
        lines.append("=" * 60)
        lines.append(f"Generated: {report.generated_at}")
        lines.append(f"Total Points: {report.total_points}")
        lines.append(f"Valid Points: {report.valid_points}")
        lines.append(f"Invalid Points: {report.invalid_points}")
        lines.append(f"Validation Rate: {report.validation_rate:.2%}")
        lines.append("")
        
        # Summary
        lines.append("SUMMARY")
        lines.append("-" * 30)
        lines.append(f"Total Errors: {report.summary['total_errors']}")
        lines.append(f"Total Warnings: {report.summary['total_warnings']}")
        lines.append(f"Validation Rules Used: {', '.join(report.summary['validation_rules_used'])}")
        lines.append("")
        
        # Errors by rule
        if report.summary['errors_by_rule']:
            lines.append("ERRORS BY RULE")
            lines.append("-" * 30)
            for rule, count in report.summary['errors_by_rule'].items():
                lines.append(f"{rule}: {count}")
            lines.append("")
        
        # Detailed results
        lines.append("DETAILED RESULTS")
        lines.append("-" * 30)
        for i, result in enumerate(report.results, 1):
            status = "VALID" if result.is_valid else "INVALID"
            lines.append(f"Point {i}: {status}")
            lines.append(f"  Data: {str(result.data_point)}")
            lines.append(f"  Rules: {', '.join(result.validation_rules)}")
            if result.errors:
                lines.append(f"  Errors: {', '.join(result.errors)}")
            if result.warnings:
                lines.append(f"  Warnings: {', '.join(result.warnings)}")
            lines.append("")
        
        return "\n".join(lines)