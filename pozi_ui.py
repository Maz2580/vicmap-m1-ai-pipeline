import tkinter as tk
from tkinter import ttk, messagebox
import threading
from pathlib import Path
import logging
from datetime import datetime
import queue
import sys
from dotenv import load_dotenv
import os

from pozi_runner import (
    POZI_DIR, POZI_EXE, TASKS_DIR, OUTPUT_DIR, 
    POZI_TASKS, verify_pozi_installation,
    run_pozi_tasks, find_generated_m1_file
)
from email_monitor import check_email_for_download_url
from download_extract import download_data, extract_data, setup_directories, clean_existing_data
from config import get_download_url, save_download_url
import fme_runner_new as fme_runner

logger = logging.getLogger(__name__)

class LogHandler(logging.Handler):
    """Custom logging handler that redirects logs to both console and UI."""
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        log_entry = self.format(record)
        self.queue.put(log_entry)

class PoziConnectUI:
    def __init__(self, root):
        self.root = root
        self.root.title("M1 Processor")
        self.root.geometry("600x800")  # Increased size for more content
        
        # Configure style for a cleaner look
        self.style = ttk.Style()
        self.style.configure('Header.TLabelframe.Label', font=('Segoe UI', 9, 'bold'))
        self.style.configure('Status.TLabel', font=('Segoe UI', 9))
        
        # Set up logging queue
        self.log_queue = queue.Queue()
        self.setup_logging()
        
        # Create main frame with padding
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Initialize flags
        self.is_running = False
        self.monitoring = False
        
        # Load environment variables
        load_dotenv()
        
        # Add tooltips for sections
        self.tooltips = {}
        
        self.create_widgets()
        self.update_log_display()
        
        # Running flag
        self.is_running = False

    def setup_logging(self):
        """Set up logging to both file and UI."""
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        # Add handler for UI
        ui_handler = LogHandler(self.log_queue)
        ui_handler.setFormatter(formatter)
        logger.addHandler(ui_handler)

    def create_widgets(self):
        """Create and arrange all UI widgets."""
        # Status Section
        status_frame = ttk.LabelFrame(
            self.main_frame, 
            text="Status",
            style='Header.TLabelframe'
        )
        status_frame.pack(fill=tk.X, pady=(0, 5))
        
        status_content = ttk.Frame(status_frame)
        status_content.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(
            status_content,
            text="Pozi Connect:",
            style='Status.TLabel'
        ).pack(side=tk.LEFT)
        
        self.pozi_status = ttk.Label(
            status_content,
            text="Ready",
            foreground="green",
            style='Status.TLabel'
        )
        self.pozi_status.pack(side=tk.LEFT, padx=(5, 0))
        
        # 1. Email Monitoring Section
        email_frame = ttk.LabelFrame(
            self.main_frame,
            text="1. Email Monitoring",
            style='Header.TLabelframe'
        )
        email_frame.pack(fill=tk.X, pady=(0, 5))
        
        email_content = ttk.Frame(email_frame)
        email_content.pack(fill=tk.X, padx=5, pady=2)
        
        self.email_status = ttk.Label(
            email_content,
            text="Not Monitoring",
            foreground="gray",
            style='Status.TLabel'
        )
        self.email_status.pack(side=tk.LEFT)
        
        self.monitor_button = ttk.Button(
            email_content,
            text="Start Monitoring",
            command=self.toggle_email_monitoring
        )
        self.monitor_button.pack(side=tk.RIGHT)
        
        # 2. Download and Extract Section
        download_frame = ttk.LabelFrame(
            self.main_frame,
            text="2. Data Download & Extract",
            style='Header.TLabelframe'
        )
        download_frame.pack(fill=tk.X, pady=(0, 5))
        
        download_content = ttk.Frame(download_frame)
        download_content.pack(fill=tk.X, padx=5, pady=2)
        
        self.download_status = ttk.Label(
            download_content,
            text="No Data Available",
            foreground="gray",
            style='Status.TLabel'
        )
        self.download_status.pack(side=tk.LEFT)
        
        self.download_button = ttk.Button(
            download_content,
            text="Download & Extract",
            command=self.download_and_extract,
            state=tk.DISABLED
        )
        self.download_button.pack(side=tk.RIGHT)
        
        # 3. FME Processing Section
        fme_frame = ttk.LabelFrame(
            self.main_frame,
            text="3. FME Processing",
            style='Header.TLabelframe'
        )
        fme_frame.pack(fill=tk.X, pady=(0, 5))
        
        fme_content = ttk.Frame(fme_frame)
        fme_content.pack(fill=tk.X, padx=5, pady=2)
        
        self.fme_status = ttk.Label(
            fme_content,
            text="Waiting for Data",
            foreground="gray",
            style='Status.TLabel'
        )
        self.fme_status.pack(side=tk.LEFT)
        
        self.fme_button = ttk.Button(
            fme_content,
            text="Run FME Processing",
            command=self.run_fme_processing,
            state=tk.DISABLED
        )
        self.fme_button.pack(side=tk.RIGHT)
        
        # 4. Pozi Tasks Section
        tasks_frame = ttk.LabelFrame(
            self.main_frame,
            text="4. Pozi Tasks",
            style='Header.TLabelframe'
        )
        tasks_frame.pack(fill=tk.X, pady=(0, 5))
        
        tasks_content = ttk.Frame(tasks_frame)
        tasks_content.pack(fill=tk.X, padx=5, pady=2)
        
        # Task checkboxes
        self.task_vars = []
        for task in POZI_TASKS:
            var = tk.BooleanVar(value=True)
            self.task_vars.append(var)
            cb = ttk.Checkbutton(
                tasks_content,
                text=task['name'],
                variable=var,
                style='Status.TLabel'
            )
            cb.pack(anchor=tk.W)
            
        # Progress Section
        progress_frame = ttk.LabelFrame(
            self.main_frame,
            text="Progress",
            style='Header.TLabelframe'
        )
        progress_frame.pack(fill=tk.X, pady=(0, 5))
        
        progress_content = ttk.Frame(progress_frame)
        progress_content.pack(fill=tk.X, padx=5, pady=2)
        
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(
            progress_content,
            textvariable=self.progress_var,
            style='Status.TLabel'
        ).pack(anchor=tk.W)
        
        self.progress = ttk.Progressbar(
            progress_content,
            mode='determinate'
        )
        self.progress.pack(fill=tk.X, pady=(2, 0))
        
        # Log Section
        log_frame = ttk.LabelFrame(
            self.main_frame,
            text="Log",
            style='Header.TLabelframe'
        )
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Create log display with scrollbar in a container
        log_container = ttk.Frame(log_frame)
        log_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        
        self.log_display = tk.Text(
            log_container,
            wrap=tk.WORD,
            font=('Consolas', 9),
            background='white',
            relief=tk.SUNKEN,
            borderwidth=1
        )
        scrollbar = ttk.Scrollbar(
            log_container,
            orient=tk.VERTICAL,
            command=self.log_display.yview
        )
        self.log_display.configure(yscrollcommand=scrollbar.set)
        
        self.log_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Buttons at the bottom
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.start_button = ttk.Button(
            button_frame,
            text="Start Processing",
            command=self.start_processing,
            style='Status.TButton'
        )
        self.start_button.pack(side=tk.LEFT, padx=(0, 5))
        
        self.cancel_button = ttk.Button(
            button_frame,
            text="Cancel",
            command=self.cancel_processing,
            state=tk.DISABLED,
            style='Status.TButton'
        )
        self.cancel_button.pack(side=tk.LEFT)
        
        # Verify installation
        self.verify_installation()

    def verify_installation(self):
        """Verify Pozi Connect installation and update status."""
        try:
            verify_pozi_installation()
            self.pozi_status.configure(text="Ready", foreground="green")
        except Exception as e:
            self.pozi_status.configure(text="Not Found", foreground="red")
            messagebox.showerror("Error", str(e))
            self.start_button.configure(state=tk.DISABLED)

    def update_log_display(self):
        """Update log display with new messages from queue."""
        while True:
            try:
                log_message = self.log_queue.get_nowait()
                self.log_display.insert(tk.END, log_message + "\n")
                self.log_display.see(tk.END)
                self.log_queue.task_done()
            except queue.Empty:
                break
        
        self.root.after(100, self.update_log_display)

    def start_processing(self):
        """Start processing M1 tasks."""
        if self.is_running:
            return
            
        self.is_running = True
        self.start_button.configure(state=tk.DISABLED)
        self.cancel_button.configure(state=tk.NORMAL)
        self.progress_var.set("Processing...")
        self.progress['value'] = 0
        
        # Clear log display
        self.log_display.delete(1.0, tk.END)
        
        # Start processing in a separate thread
        thread = threading.Thread(target=self.process_tasks)
        thread.daemon = True
        thread.start()

    def toggle_email_monitoring(self):
        """Toggle email monitoring on/off."""
        if self.monitor_button['text'] == "Start Monitoring":
            self.monitor_button['text'] = "Stop Monitoring"
            self.email_status.configure(text="Monitoring...", foreground="green")
            self.monitoring = True
            self.start_email_monitoring()
        else:
            self.monitor_button['text'] = "Start Monitoring"
            self.email_status.configure(text="Not Monitoring", foreground="gray")
            self.monitoring = False
            self.stop_email_monitoring()
    
    def start_email_monitoring(self):
        """Start monitoring emails for data updates."""
        def check_emails():
            if not self.monitoring:
                return
                
            try:
                result = check_email_for_download_url()
                
                if result:
                    url, date = result
                    save_download_url(url, date)
                    self.download_button.configure(state=tk.NORMAL)
                    self.download_status.configure(
                        text=f"Data Available ({date.strftime('%Y-%m-%d %H:%M')})",
                        foreground="green"
                    )
                    self.log_display.insert(tk.END, f"New data available from {date.strftime('%Y-%m-%d %H:%M')}\n")
                    self.log_display.see(tk.END)
                    
            except Exception as e:
                logger.error(f"Email monitoring error: {e}")
                self.log_display.insert(tk.END, f"Email monitoring error: {e}\n")
                self.log_display.see(tk.END)
                
            # Schedule next check in 5 minutes if still monitoring
            if self.monitoring:
                self.root.after(300000, check_emails)
            
        # Start first check
        check_emails()
        
    def stop_email_monitoring(self):
        """Stop monitoring emails."""
        self.monitoring = False
        
    def download_and_extract(self):
        """Download and extract data from available URL."""
        self.download_button.configure(state=tk.DISABLED)
        self.download_status.configure(text="Downloading...", foreground="blue")
        
        def process():
            try:
                url = get_download_url()
                if not url:
                    raise ValueError("No download URL available")
                    
                # Set up directories
                setup_directories()
                clean_existing_data()
                
                # Download and extract
                zip_path = download_data(url)
                extract_data(zip_path)
                
                self.download_status.configure(text="Data Ready", foreground="green")
                self.fme_button.configure(state=tk.NORMAL)
                self.fme_status.configure(text="Ready to Process", foreground="blue")
                
                self.log_display.insert(tk.END, "Data downloaded and extracted successfully\n")
                self.log_display.see(tk.END)
                
            except Exception as e:
                logger.error(f"Download error: {e}")
                self.download_status.configure(text="Download Failed", foreground="red")
                self.download_button.configure(state=tk.NORMAL)
                self.log_display.insert(tk.END, f"Download error: {e}\n")
                self.log_display.see(tk.END)
                messagebox.showerror("Error", str(e))
                
        # Run in separate thread
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()
        
    def run_fme_processing(self):
        """Run FME processing on the extracted data."""
        self.fme_button.configure(state=tk.DISABLED)
        self.fme_status.configure(text="Processing...", foreground="blue")
        
        def process():
            try:
                # Verify FME installation
                fme_runner.verify_fme_installation()
                
                # Run the main workflow
                result = fme_runner.run_fme(
                    fme_runner.MAIN_WORKFLOW,
                    test_mode=False
                )
                
                if result.returncode == 0:
                    self.fme_status.configure(text="Processing Complete", foreground="green")
                    self.start_button.configure(state=tk.NORMAL)
                    self.progress_var.set("Ready for Pozi Tasks")
                    self.log_display.insert(tk.END, "FME processing completed successfully\n")
                else:
                    raise RuntimeError(f"FME processing failed with code {result.returncode}")
                    
            except Exception as e:
                logger.error(f"FME processing error: {e}")
                self.fme_status.configure(text="Processing Failed", foreground="red")
                self.fme_button.configure(state=tk.NORMAL)
                self.log_display.insert(tk.END, f"FME processing error: {e}\n")
                messagebox.showerror("Error", str(e))
                
            self.log_display.see(tk.END)
                
        # Run in separate thread
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()
    
    def process_tasks(self):
        """Process M1 tasks in a separate thread."""
        try:
            # Run tasks
            result = run_pozi_tasks()
            
            if result.returncode == 0:
                self.progress_var.set("Completed Successfully")
                self.progress['value'] = 100
                
                # Check for generated M1 file
                m1_file = find_generated_m1_file()
                if m1_file:
                    messagebox.showinfo(
                        "Success", 
                        f"Processing completed successfully!\n\nGenerated M1 file:\n{m1_file}"
                    )
            else:
                self.progress_var.set("Failed")
                messagebox.showerror(
                    "Error",
                    f"Processing failed with return code {result.returncode}"
                )
                
        except Exception as e:
            self.progress_var.set("Error")
            messagebox.showerror("Error", str(e))
            
        finally:
            self.is_running = False
            self.start_button.configure(state=tk.NORMAL)
            self.cancel_button.configure(state=tk.DISABLED)

    def cancel_processing(self):
        """Cancel the current processing operation."""
        if not self.is_running:
            return
            
        if messagebox.askyesno("Confirm Cancel", "Are you sure you want to cancel processing?"):
            self.progress_var.set("Cancelling...")
            # Implement cancellation logic here
            self.is_running = False
            self.start_button.configure(state=tk.NORMAL)
            self.cancel_button.configure(state=tk.DISABLED)
            self.progress_var.set("Cancelled")

def main():
    root = tk.Tk()
    app = PoziConnectUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()