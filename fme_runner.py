import subprocess
import logging
import time
import os
from pathlib import Path
from datetime import datetime, timedelta
from config import LOG_DIR, FME_WORKSPACE, FME_EXE

logger = logging.getLogger(__name__)

def verify_fme_installation():
    """Verify FME is installed and executable."""
    if not FME_EXE.exists():
        raise FileNotFoundError(
            f"FME executable not found at {FME_EXE}. "
            "Please verify FME is installed or set M1_FME_EXE environment variable."
        )
    logger.info(f"FME installation verified at: {FME_EXE}")

def verify_workspace_access(workspace: Path):
    """Verify we can access the FME workspace."""
    if not workspace.is_absolute():
        raise ValueError(f"Workspace path must be absolute: {workspace}")
        
    if not workspace.exists():
        raise FileNotFoundError(f"FME workspace not found: {workspace}")
    
    if workspace.suffix.lower() != '.fmw':
        raise ValueError(f"File does not appear to be an FME workspace: {workspace}")
    
    if not os.access(workspace, os.R_OK):
        raise PermissionError(f"Cannot read FME workspace at {workspace}")
    
    logger.info(f"Workspace verified: {workspace}")

def parse_fme_output(stdout: str, logger) -> dict:
    """Parse FME output to extract execution details.
    
    Returns:
        dict with workspaces_run list and summary info
    """
    workspaces_run = []
    current_workspace = None
    start_time = None
    
    for line in stdout.splitlines():
        # Track workspace execution
        if 'Running FME with command line' in line and '.fmw' in line:
            try:
                timestamp = line.split('|')[0].strip()
                # Extract workspace name from path
                workspace_match = line.split("'")
                if len(workspace_match) > 1:
                    workspace_path = workspace_match[1]
                    current_workspace = Path(workspace_path).name
                else:
                    current_workspace = "Unknown"
                start_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                logger.info(f"Started: {current_workspace}")
            except Exception as e:
                logger.debug(f"Could not parse workspace start: {e}")
        
        elif 'Successfully ran workspace' in line and current_workspace:
            try:
                timestamp = line.split('|')[0].strip()
                end_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                duration = end_time - start_time
                workspaces_run.append({
                    'name': current_workspace,
                    'start': start_time,
                    'end': end_time,
                    'duration': duration
                })
                logger.info(f"Completed: {current_workspace} ({duration.total_seconds():.1f}s)")
            except Exception as e:
                logger.debug(f"Could not parse workspace completion: {e}")
        
        # Log important messages
        if any(keyword in line.upper() for keyword in ['ERROR', 'FAIL']):
            logger.error(line)
        elif 'WARN' in line.upper():
            logger.warning(line)
        elif 'TRANSLATION SUCCESSFUL' in line.upper():
            logger.info(line)
        else:
            logger.debug(line)
    
    return {
        'workspaces_run': workspaces_run,
        'total_workspaces': len(workspaces_run)
    }

def print_execution_summary(execution_info: dict, logger):
    """Print a formatted summary of workspace execution."""
    workspaces_run = execution_info.get('workspaces_run', [])
    
    if not workspaces_run:
        logger.warning("No workspace execution details found in output")
        return
    
    logger.info("\n" + "="*70)
    logger.info("WORKSPACE EXECUTION SUMMARY")
    logger.info("="*70)
    
    total_duration = timedelta()
    for i, ws in enumerate(workspaces_run, 1):
        logger.info(f"\n{i}. {ws['name']}")
        logger.info(f"   Started:  {ws['start'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   Finished: {ws['end'].strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"   Duration: {ws['duration'].total_seconds():.1f} seconds")
        total_duration += ws['duration']
    
    logger.info("\n" + "-"*70)
    logger.info(f"Total workspaces executed: {len(workspaces_run)}")
    logger.info(f"Total execution time: {total_duration.total_seconds():.1f} seconds ({total_duration.total_seconds()/60:.1f} minutes)")
    logger.info("="*70 + "\n")

def run_fme(workspace: Path = None, parameters: dict = None, test_mode: bool = False) -> subprocess.CompletedProcess:
    """Run an FME workspace with parameters.
    
    Args:
        workspace: Path to FME workspace (defaults to FME_WORKSPACE from config)
        parameters: Dictionary of parameters to pass to FME
        test_mode: If True, adds TEST_MODE parameter
        
    Returns:
        subprocess.CompletedProcess object with execution results
    """
    # Use default workspace if none provided
    if workspace is None:
        workspace = FME_WORKSPACE
    
    verify_fme_installation()
    verify_workspace_access(workspace)
    
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"fme_run_{timestamp}.log"
    
    # FME's default log file location (same directory as workspace with .log extension)
    fme_log_file = workspace.with_suffix('.log')
    
    # Build command as list for proper argument handling
    cmd = [
        str(FME_EXE),
        str(workspace),
        f"--LOG_FILE={log_file}",
        "--LOG_FILTER_MASK=INFORM"  # Less verbose than DETAIL
    ]
    
    # Add test mode parameter if needed
    if test_mode:
        cmd.append("--TEST_MODE=true")
    
    # Add any additional parameters
    if parameters:
        for key, value in parameters.items():
            cmd.append(f"--{key}={value}")
    
    logger.info("="*70)
    logger.info("FME WORKSPACE EXECUTION")
    logger.info("="*70)
    logger.info(f"Workspace: {workspace}")
    logger.info(f"Test mode: {test_mode}")
    logger.info(f"Log file: {log_file}")
    logger.info(f"FME log: {fme_log_file}")
    if parameters:
        logger.info(f"Parameters: {parameters}")
    logger.info("="*70 + "\n")
    
    try:
        # Start the process
        logger.info("Starting FME execution...")
        start_time = datetime.now()
        
        # subprocess.run with a list argv handles Windows paths-with-spaces
        # fine without invoking the shell — passing shell=True would mean a
        # poisoned config value could inject shell metacharacters. Security
        # audit H-4.
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour
        )
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        # Write captured output to our log file
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("="*70 + "\n")
                f.write("FME WORKSPACE EXECUTION LOG\n")
                f.write("="*70 + "\n")
                f.write(f"Workspace: {workspace}\n")
                f.write(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration.total_seconds():.1f} seconds\n")
                f.write(f"Return Code: {result.returncode}\n")
                f.write("="*70 + "\n\n")
                
                if result.stdout:
                    f.write("STANDARD OUTPUT:\n")
                    f.write("-"*70 + "\n")
                    f.write(result.stdout)
                    f.write("\n" + "-"*70 + "\n\n")
                
                if result.stderr:
                    f.write("STANDARD ERROR:\n")
                    f.write("-"*70 + "\n")
                    f.write(result.stderr)
                    f.write("\n" + "-"*70 + "\n\n")
                
                f.write("="*70 + "\n")
                f.write("END OF LOG\n")
                f.write("="*70 + "\n")
            
            logger.info(f"Execution log saved to: {log_file}")
        except Exception as e:
            logger.warning(f"Could not write log file: {e}")
        
        # Parse and log the results
        if result.stdout:
            execution_info = parse_fme_output(result.stdout, logger)
            print_execution_summary(execution_info, logger)
        
        if result.stderr:
            logger.error("\nFME Standard Error Output:")
            for line in result.stderr.splitlines():
                logger.error(line)
        
        # Check result
        logger.info("\n" + "="*70)
        if result.returncode == 0:
            logger.info("✓ FME WORKSPACE COMPLETED SUCCESSFULLY")
            logger.info(f"Total time: {duration.total_seconds():.1f} seconds ({duration.total_seconds()/60:.1f} minutes)")
            
            # Check if FME's log file exists and show its location
            if fme_log_file.exists():
                log_size = fme_log_file.stat().st_size / 1024  # Size in KB
                logger.info(f"FME log file: {fme_log_file} ({log_size:.1f} KB)")
        else:
            logger.error("✗ FME WORKSPACE FAILED")
            logger.error(f"Return code: {result.returncode}")
            logger.error(f"Total time: {duration.total_seconds():.1f} seconds")
            if fme_log_file.exists():
                logger.error(f"Check FME log for details: {fme_log_file}")
        
        logger.info("="*70 + "\n")
        return result
        
    except subprocess.TimeoutExpired:
        logger.error("FME process timed out after 1 hour")
        raise
    except Exception as e:
        logger.error(f"Error running FME: {e}")
        raise

def main():
    """Main execution function."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Display configuration
        print("\n" + "="*70)
        print("FME WORKFLOW RUNNER")
        print("="*70)
        print(f"FME Executable: {FME_EXE}")
        print(f"Workspace:      {FME_WORKSPACE}")
        print(f"Log Directory:  {LOG_DIR}")
        print("\nNote: This process may take 10-15 minutes.")
        print("="*70)
        
        response = input("\nWould you like to continue? (y/n): ").lower().strip()
        
        if response != 'y':
            logger.info("Operation cancelled by user")
            return
        
        # Run the workspace
        logger.info("Starting FME workflow execution...\n")
        result = run_fme(test_mode=False)
        
        if result.returncode == 0:
            print("\n✓ FME workflow completed successfully!")
            print(f"Check logs at: {LOG_DIR}")
        else:
            print("\n✗ FME workflow failed - check logs for details")
            print(f"Log directory: {LOG_DIR}")
            return 1
            
    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user (Ctrl+C)")
        return 130
    except Exception as e:
        logger.exception(f"Error running FME workflow: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())