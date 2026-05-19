"""
Enhanced logging for M1 Automation with user-friendly messages
Provides meaningful, actionable insights with progress tracking
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional
import time


class M1Logger:
    """Enhanced logger with meaningful user messages and progress tracking"""
    
    def __init__(self, workflow_name: str, send_log_callback=None):
        """
        Initialize enhanced logger
        
        Args:
            workflow_name: Name of the workflow (e.g., "AI_Validation")
            send_log_callback: Optional callback function to send logs to main app
        """
        self.workflow_name = workflow_name
        self.start_time = None
        self.current_step = 0
        self.total_steps = 0
        self.logger = logging.getLogger(f'M1_{workflow_name}')
        self.send_log_callback = send_log_callback
        
    def _send_log(self, level: str, message: str):
        """Send log to main app if callback is available"""
        if self.send_log_callback:
            try:
                self.send_log_callback(level, message)
            except Exception:
                pass  # Don't fail if callback fails
        
        # Also log to standard logger
        if level == 'INFO':
            self.logger.info(message)
        elif level == 'WARNING':
            self.logger.warning(message)
        elif level == 'ERROR':
            self.logger.error(message)
        
    def start_workflow(self, total_steps: int, description: str):
        """Start a workflow with progress tracking"""
        self.start_time = time.time()
        self.total_steps = total_steps
        self.current_step = 0
        
        self.log_user_info(f"🚀 {description}")
        self.log_user_info(f"📋 {total_steps} steps planned")
        self.log_user_info("=" * 60)
        
    def step_started(self, step_name: str, details: str = ""):
        """Log step start with progress"""
        self.current_step += 1
        progress = (self.current_step / self.total_steps * 100) if self.total_steps > 0 else 0
        
        self.log_user_info(f"[Step {self.current_step}/{self.total_steps}] {step_name} ({progress:.0f}%)")
        if details:
            self.log_user_info(f"   ℹ️  {details}")
            
    def step_progress(self, message: str, count: Optional[int] = None, total: Optional[int] = None):
        """Log progress within a step"""
        if count is not None and total is not None:
            percentage = (count / total * 100) if total > 0 else 0
            self.log_user_info(f"   → {message} ({count}/{total} - {percentage:.0f}%)")
        else:
            self.log_user_info(f"   → {message}")
            
    def step_completed(self, step_name: str, duration: Optional[float] = None, result_summary: str = ""):
        """Log step completion"""
        duration_str = f" ({duration:.1f}s)" if duration else ""
        self.log_user_info(f"   ✅ {step_name} completed{duration_str}")
        if result_summary:
            self.log_user_info(f"   📊 {result_summary}")
            
    def step_warning(self, message: str, suggestion: str = ""):
        """Log step warning"""
        self.log_user_warning(f"   ⚠️  {message}")
        if suggestion:
            self.log_user_info(f"   💡 Suggestion: {suggestion}")
            
    def step_error(self, message: str, solution: str = ""):
        """Log step error"""
        self.log_user_error(f"   ❌ {message}")
        if solution:
            self.log_user_info(f"   🔧 Solution: {solution}")
            
    def workflow_completed(self, summary: Dict[str, Any]):
        """Log workflow completion with summary"""
        duration = time.time() - self.start_time if self.start_time else 0
        
        self.log_user_info("=" * 60)
        self.log_user_info(f"🎉 {self.workflow_name.upper()} COMPLETED SUCCESSFULLY!")
        
        # Format duration nicely
        if duration < 60:
            duration_str = f"{duration:.1f} seconds"
        elif duration < 3600:
            minutes = duration / 60
            duration_str = f"{minutes:.1f} minutes"
        else:
            hours = duration / 3600
            duration_str = f"{hours:.1f} hours"
        
        self.log_user_info(f"⏱️  Total time: {duration_str}")
        
        for key, value in summary.items():
            self.log_user_info(f"📈 {key}: {value}")
            
        self.log_user_info("=" * 60)
        
    def log_user_info(self, message: str):
        """Log info message in user-friendly format"""
        full_message = f"[{self.workflow_name}] {message}"
        self._send_log('INFO', full_message)
        
    def log_user_warning(self, message: str):
        """Log warning message"""
        full_message = f"[{self.workflow_name}] {message}"
        self._send_log('WARNING', full_message)
        
    def log_user_error(self, message: str):
        """Log error message"""
        full_message = f"[{self.workflow_name}] {message}"
        self._send_log('ERROR', full_message)

