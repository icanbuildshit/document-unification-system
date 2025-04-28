"""
Analytics Orchestrator for managing system metrics and operational insights.
"""

import logging
import uuid
import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class AnalyticsOrchestrator:
    """
    Orchestrates analytics and metrics collection operations.
    
    Responsible for:
    1. Coordinating data collection for performance metrics
    2. Managing system utilization and bottleneck detection
    3. Tracking document processing statistics
    4. Generating operational insights and recommendations
    5. Handling batch analytics processing
    """
    
    def __init__(self):
        """Initialize the analytics orchestrator."""
        self.orchestrator_id = f"analytics-orch-{uuid.uuid4().hex[:8]}"
        self.metrics_cache = {}  # In-memory cache of recent metrics
        self.performance_thresholds = {
            "document_parse_time_ms": 5000,  # 5 seconds
            "storage_write_time_ms": 2000,   # 2 seconds
            "cpu_utilization": 80,           # 80%
            "memory_utilization": 70         # 70%
        }
        logger.info(f"Analytics Orchestrator {self.orchestrator_id} initialized.")
    
    async def record_metric(self, metric_type: str, component_id: str, value: float, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Record a metric value for a component.
        
        Args:
            metric_type: Type of metric being recorded
            component_id: ID of the component the metric is for
            value: Value of the metric
            context: Additional context about the metric
            
        Returns:
            Dictionary containing recording results
        """
        logger.info(f"Recording {metric_type} metric for {component_id}: {value}")
        
        # Create metric entry
        metric_entry = {
            "metric_id": f"metric-{uuid.uuid4().hex}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metric_type": metric_type,
            "component_id": component_id,
            "value": value,
            "context": context or {}
        }
        
        # Add to metrics cache
        if component_id not in self.metrics_cache:
            self.metrics_cache[component_id] = {}
        
        if metric_type not in self.metrics_cache[component_id]:
            self.metrics_cache[component_id][metric_type] = []
            
        self.metrics_cache[component_id][metric_type].append(metric_entry)
        
        # Keep only recent metrics (last 24 hours)
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        self.metrics_cache[component_id][metric_type] = [
            m for m in self.metrics_cache[component_id][metric_type] 
            if datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")) > cutoff_time
        ]
        
        # Check thresholds and generate alerts if needed
        alerts = []
        if metric_type in self.performance_thresholds:
            threshold = self.performance_thresholds[metric_type]
            if metric_type.endswith("_time_ms") and value > threshold:
                alerts.append({
                    "alert_type": "performance_degradation",
                    "component_id": component_id,
                    "metric_type": metric_type,
                    "value": value,
                    "threshold": threshold,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
            elif metric_type.endswith("_utilization") and value > threshold:
                alerts.append({
                    "alert_type": "resource_constraint",
                    "component_id": component_id,
                    "metric_type": metric_type,
                    "value": value,
                    "threshold": threshold,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
        
        # Write to persistent storage (async)
        await self._write_metric_to_file(metric_entry)
        
        result = {
            "metric_id": metric_entry["metric_id"],
            "timestamp": metric_entry["timestamp"],
            "alerts": alerts,
            "status": "recorded"
        }
        
        return result
    
    async def _write_metric_to_file(self, metric_entry: Dict[str, Any]) -> None:
        """
        Write a metric entry to the appropriate metrics file.
        
        Args:
            metric_entry: Metric entry to write
        """
        # Create metrics directory if it doesn't exist
        metrics_dir = os.path.join("logs", "metrics")
        os.makedirs(metrics_dir, exist_ok=True)
        
        # Determine metrics file based on metric type
        metric_type = metric_entry["metric_type"]
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        
        if metric_type.startswith("document_"):
            metrics_file = os.path.join(metrics_dir, f"document_metrics_{date_str}.jsonl")
        elif metric_type.startswith("system_"):
            metrics_file = os.path.join(metrics_dir, f"system_metrics_{date_str}.jsonl")
        elif metric_type.startswith("orchestrator_"):
            metrics_file = os.path.join(metrics_dir, f"orchestrator_metrics_{date_str}.jsonl")
        else:
            metrics_file = os.path.join(metrics_dir, f"general_metrics_{date_str}.jsonl")
        
        # Write metric entry to file
        try:
            with open(metrics_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(metric_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write metric entry to file: {e}")
    
    async def get_component_metrics(self, component_id: str, metric_types: Optional[List[str]] = None, start_time: Optional[str] = None, end_time: Optional[str] = None) -> Dict[str, Any]:
        """
        Get metrics for a component with optional filtering by metric type and time range.
        
        Args:
            component_id: ID of the component to get metrics for
            metric_types: Optional list of metric types to filter by
            start_time: ISO format start time for the query
            end_time: ISO format end time for the query
            
        Returns:
            Dictionary containing metrics data
        """
        logger.info(f"Getting metrics for component {component_id}")
        
        if component_id not in self.metrics_cache:
            return {
                "component_id": component_id,
                "metrics": {},
                "status": "success"
            }
        
        # Convert times to datetime objects if provided
        start_dt = None
        end_dt = None
        
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            except ValueError:
                return {"status": "error", "message": "Invalid start_time format"}
                
        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError:
                return {"status": "error", "message": "Invalid end_time format"}
        
        # Filter metrics
        filtered_metrics = {}
        component_metrics = self.metrics_cache[component_id]
        
        for metric_type, metrics in component_metrics.items():
            if metric_types and metric_type not in metric_types:
                continue
                
            filtered_metrics[metric_type] = []
            
            for metric in metrics:
                # Check time range
                if start_dt or end_dt:
                    metric_dt = datetime.fromisoformat(metric["timestamp"].replace("Z", "+00:00"))
                    if start_dt and metric_dt < start_dt:
                        continue
                    if end_dt and metric_dt > end_dt:
                        continue
                
                filtered_metrics[metric_type].append(metric)
        
        # Calculate statistics for each metric type
        metrics_stats = {}
        for metric_type, metrics in filtered_metrics.items():
            if not metrics:
                continue
                
            values = [m["value"] for m in metrics]
            metrics_stats[metric_type] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "latest": values[-1] if values else None,
                "latest_timestamp": metrics[-1]["timestamp"] if metrics else None
            }
        
        return {
            "component_id": component_id,
            "metrics": filtered_metrics,
            "stats": metrics_stats,
            "status": "success"
        }
    
    async def generate_system_report(self) -> Dict[str, Any]:
        """
        Generate a system-wide analytics report.
        
        Returns:
            Dictionary containing the system report
        """
        logger.info("Generating system analytics report")
        
        # TODO: Implement actual report generation logic
        # This is a placeholder implementation
        
        # Collect system-wide metrics
        system_metrics = {
            "document_count": 42,  # Placeholder
            "total_processing_time_ms": 185000,  # Placeholder
            "average_processing_time_ms": 4400,  # Placeholder
            "system_uptime_hours": 72,  # Placeholder
            "error_rate": 0.02,  # Placeholder (2%)
            "resource_utilization": {
                "cpu": 35,  # Placeholder (35%)
                "memory": 42,  # Placeholder (42%)
                "disk": 28  # Placeholder (28%)
            }
        }
        
        # Generate insights
        insights = [
            {
                "insight_type": "performance",
                "description": "Document parsing is the most time-consuming operation",
                "recommendation": "Consider parallel processing for large documents",
                "priority": "medium"
            },
            {
                "insight_type": "utilization",
                "description": "System resources are being utilized efficiently",
                "recommendation": "Continue monitoring for changes in utilization patterns",
                "priority": "low"
            },
            {
                "insight_type": "errors",
                "description": "Error rate is within acceptable limits",
                "recommendation": "No action needed at this time",
                "priority": "low"
            }
        ]
        
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "report_id": f"report-{uuid.uuid4().hex}",
            "system_metrics": system_metrics,
            "insights": insights,
            "status": "success"
        } 