import subprocess
import logging
import os
from pathlib import Path
from datetime import datetime
from config import (
    LOG_DIR,
    POZI_DIR,
    POZI_EXE,
    POZI_TASKS_DIR,
    POZI_OUTPUT_DIR,
    POZI_TASKS,
    POZI_RECIPE_DIR
)

logger = logging.getLogger(__name__)

def verify_pozi_installation():
    """Verify Pozi Connect is installed and executable."""
    if not POZI_EXE.exists():
        raise FileNotFoundError(
            f"Pozi Connect executable not found at {POZI_EXE}. "
            "Please verify Pozi Connect is installed or update M1_POZI_DIR environment variable."
        )
    logger.info(f"Pozi Connect installation verified at: {POZI_EXE}")
    
    # Verify tasks directory exists
    if not POZI_TASKS_DIR.exists():
        logger.warning(f"Tasks directory not found at: {POZI_TASKS_DIR}")
    else:
        logger.info(f"Tasks directory verified: {POZI_TASKS_DIR}")

def create_recipe_file() -> Path:
    """Create a recipe file containing the tasks to run.
    
    Returns:
        Path to the created recipe file
    """
    POZI_RECIPE_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recipe_path = POZI_RECIPE_DIR / f"m1_tasks_{timestamp}.txt"
    
    logger.info(f"Creating recipe file: {recipe_path}")
    with open(recipe_path, 'w') as f:
        for task in POZI_TASKS:
            f.write(f"{task['ini']}\n")
            logger.debug(f"Added to recipe: {task['ini']}")
    
    logger.info("Recipe file created successfully")
    return recipe_path

def find_generated_m1_file() -> Path:
    """Find the most recently generated M1 file in the output directory.
    
    Returns:
        Path to the most recent M1 file, or None if not found
    """
    if not POZI_OUTPUT_DIR.exists():
        logger.warning(f"Output directory not found: {POZI_OUTPUT_DIR}")
        return None
        
    # List all M1 files and sort by modification time
    m1_files = list(POZI_OUTPUT_DIR.glob("M1_*.csv"))
    if not m1_files:
        logger.warning(f"No M1 files found in: {POZI_OUTPUT_DIR}")
        return None
        
    # Return the most recently modified file
    most_recent = max(m1_files, key=lambda f: f.stat().st_mtime)
    logger.info(f"Found M1 file: {most_recent}")
    return most_recent

def run_pozi_tasks(timeout: int = 3600) -> subprocess.CompletedProcess:
    """Run all Pozi Connect tasks using a recipe file.
    
    Args:
        timeout: Maximum time to wait for all tasks to complete in seconds (default: 60 minutes)
        
    Returns:
        subprocess.CompletedProcess object with execution results
    """
    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"pozi_run_{timestamp}.log"
    
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create recipe file
    recipe_path = create_recipe_file()
    
    # Build command for recipe mode
    cmd_str = f'"{POZI_EXE}" --recipe="{recipe_path}"'
    
    logger.info("="*70)
    logger.info("POZI CONNECT EXECUTION")
    logger.info("="*70)
    logger.info(f"Recipe file: {recipe_path}")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Working directory: {POZI_EXE.parent}")
    logger.info("="*70 + "\n")
    
    try:
        # Start the process
        logger.info("Starting Pozi Connect tasks...")
        start_time = datetime.now()
        
        result = subprocess.run(
            cmd_str,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=True,
            cwd=str(POZI_EXE.parent)  # Run from Pozi Connect directory
        )
        
        end_time = datetime.now()
        duration = end_time - start_time
        
        # Write captured output to our log file
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("="*70 + "\n")
                f.write("POZI CONNECT EXECUTION LOG\n")
                f.write("="*70 + "\n")
                f.write(f"Recipe File: {recipe_path}\n")
                f.write(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Duration: {duration.total_seconds():.1f} seconds\n")
                f.write(f"Return Code: {result.returncode}\n")
                f.write("="*70 + "\n\n")
                
                f.write("TASKS EXECUTED:\n")
                f.write("-"*70 + "\n")
                for i, task in enumerate(POZI_TASKS, 1):
                    f.write(f"{i}. {task['name']}\n")
                    f.write(f"   INI: {task['ini']}\n")
                f.write("-"*70 + "\n\n")
                
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
        
        # Log the results to console
        if result.stdout:
            logger.info("\nPozi Connect Output:")
            for line in result.stdout.splitlines():
                # Log each line at appropriate level
                if any(keyword in line.upper() for keyword in ['ERROR', 'EXCEPTION', 'FAIL']):
                    logger.error(line)
                elif any(keyword in line.upper() for keyword in ['WARN', 'WARNING']):
                    logger.warning(line)
                else:
                    logger.debug(line)
        else:
            logger.warning("No output received from Pozi Connect")
        
        if result.stderr:
            logger.error("\nPozi Connect Standard Error:")
            for line in result.stderr.splitlines():
                logger.error(line)
        
        # Check result
        logger.info("\n" + "="*70)
        if result.returncode == 0:
            logger.info("✓ POZI CONNECT TASKS COMPLETED SUCCESSFULLY")
            logger.info(f"Total time: {duration.total_seconds():.1f} seconds ({duration.total_seconds()/60:.1f} minutes)")
            logger.info(f"Log saved: {log_file}")
        else:
            logger.error("✗ POZI CONNECT TASKS FAILED")
            logger.error(f"Return code: {result.returncode}")
            logger.error(f"Total time: {duration.total_seconds():.1f} seconds")
            logger.error(f"Log saved: {log_file}")
        logger.info("="*70 + "\n")
            
        return result
        
    except subprocess.TimeoutExpired:
        logger.error(f"Tasks timed out after {timeout/60:.1f} minutes")
        raise
    except Exception as e:
        logger.error(f"Error running Pozi Connect tasks: {e}")
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
        print("POZI CONNECT RUNNER")
        print("="*70)
        print(f"Pozi Connect:   {POZI_EXE}")
        print(f"Tasks Directory: {POZI_TASKS_DIR}")
        print(f"Output Directory: {POZI_OUTPUT_DIR}")
        print(f"Log Directory:   {LOG_DIR}")
        print("\nTasks to execute:")
        for i, task in enumerate(POZI_TASKS, 1):
            print(f"  {i}. {task['name']}")
        print("\nNote: Tasks will be executed in sequence.")
        print("      Each task may take up to 20 minutes.")
        print("="*70)
        
        response = input("\nWould you like to continue? (y/n): ").lower().strip()
        if response != 'y':
            logger.info("Operation cancelled by user")
            return 0
        
        # Verify installation
        logger.info("\nVerifying Pozi Connect installation...")
        verify_pozi_installation()
        
        # Run all tasks
        logger.info("\nStarting Pozi Connect tasks execution...\n")
        start_time = datetime.now()
        result = run_pozi_tasks()
        end_time = datetime.now()
        
        # Print execution summary
        total_duration = end_time - start_time
        
        print("\n" + "="*70)
        print("EXECUTION SUMMARY")
        print("="*70)
        print(f"Status:   {'✓ Success' if result.returncode == 0 else '✗ Failed'}")
        if result.returncode != 0:
            print(f"Error:    Return code {result.returncode}")
        print(f"Started:  {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Finished: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Duration: {total_duration.total_seconds():.1f} seconds ({total_duration.total_seconds()/60:.1f} minutes)")
        
        # Check for generated M1 file
        m1_file = find_generated_m1_file()
        if m1_file:
            file_size = m1_file.stat().st_size / 1024  # Size in KB
            file_time = datetime.fromtimestamp(m1_file.stat().st_mtime)
            print(f"\nGenerated M1 File:")
            print(f"  Path: {m1_file}")
            print(f"  Size: {file_size:.1f} KB")
            print(f"  Modified: {file_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print("\nWarning: No M1 file found in output directory")
        
        print(f"\nLogs: {LOG_DIR}")
        print("="*70)
        
        if result.returncode == 0:
            logger.info("\n✓ All Pozi Connect tasks completed successfully!")
            return 0
        else:
            logger.error("\n✗ Some Pozi Connect tasks failed. Check the logs for details.")
            return 1
            
    except KeyboardInterrupt:
        logger.warning("\nOperation cancelled by user (Ctrl+C)")
        return 130
    except Exception as e:
        logger.exception(f"Error running Pozi Connect tasks: {e}")
        return 1

if __name__ == "__main__":
    exit(main())