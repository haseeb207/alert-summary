#!/usr/bin/env python3
"""
Datadog Alert Monitoring Agent with Ollama Summarization

Monitors a directory for new Datadog alert .txt files, summarizes them using
a local Ollama LLM, posts the summary to Microsoft Teams, and archives the file.
"""

import os
import sys
import time
import signal
import logging
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

import requests
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
import ollama


# ============================================================================
# CONFIGURATION
# ============================================================================

# Load environment variables
load_dotenv()

# Environment variables with defaults
TEAMS_WEBHOOK_URL = os.getenv('TEAMS_WEBHOOK_URL')
WATCH_DIR = os.path.expanduser(os.getenv('WATCH_DIR', '~/OneDrive - Visionet/Datadog_Alerts'))
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1')
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

# Retry configuration
WEBHOOK_MAX_RETRIES = 3
WEBHOOK_RETRY_DELAYS = [1, 2, 4]  # Exponential backoff in seconds

# File stabilization configuration
FILE_STABILITY_CHECK_INTERVAL = 0.5  # seconds
FILE_STABILITY_THRESHOLD = 1.0  # seconds of no size change


# ============================================================================
# OLLAMA SYSTEM PROMPT
# ============================================================================

SYSTEM_PROMPT = """You are an expert DevOps AI assistant monitoring Datadog alerts. Your task is to read the provided raw alert text, extract the core operational metrics, and output a clean, highly structured Markdown summary suitable for a Microsoft Teams Webhook.

CRITICAL INSTRUCTIONS:
1. Ignore all massive URLs (e.g., safelinks.protection.outlook.com), email headers, and corporate disclaimer boilerplate.
2. Identify the Alert Level (e.g., P1, P2, P3 Warn), Service, Operation (API Path or GraphQL operation), Duration/Threshold, and Event Count.
3. FIRST: Classify whether this is a REST API or GraphQL API operation:
   - GraphQL indicators: mentions "GraphQL", "query", "mutation", "resolver", operation names like removeCartLines, getCartDelivery, etc.
   - REST API indicators: mentions "REST", "fetch", "/api/", "/cart/", D365, endpoint paths with slashes
4. If the alert is a recovery (Recovered/Resolved/OK) then explicitly label it as a recovery in the title and do NOT include a "Recommended Checks" section.
5. Only include "Recommended Checks" for ACTIVE alerts (non-recovery).
6. CRITICAL - Do NOT mix REST and GraphQL guidance:
   - For REST APIs ONLY: Check if it's a Cart operation. If yes, recommend verifying that the internal `fetchAPI` wrapper is used instead of raw `fetch()`, and that API caching uses the composite key (`cartId + amount`).
   - For GraphQL APIs ONLY: Recommend checking GraphQL resolver performance, upstream service latency, and query complexity limits. Do NOT mention `fetchAPI`, `fetch()`, or caching keys.
7. OUTPUT ONLY the exact Markdown format below. Do NOT include any conversational text, preambles, notes, or explanations before or after the Markdown. Output the Markdown and nothing else.

MARKDOWN FORMAT (output EXACTLY this structure, nothing more):
🚨 **[{Alert Level}] {Shortened Subject}**
* **Service:** `{Service Name}`
* **Operation:** `{API Path / GraphQL operation}`
* **Condition:** `{Threshold / Trigger}`
* **Impact:** `{Count} occurrences in {Time Window}`

**Recommended Checks:**
* {First check item}
* {Second check item, if applicable}

DO NOT output any text before or after this Markdown block. Output the Markdown and stop."""


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging():
    """Configure structured logging to both console and rotating file."""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Create logger
    logger = logging.getLogger('datadog_agent')
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # Rotating file handler (10MB max, 5 backups)
    file_handler = RotatingFileHandler(
        log_dir / 'agent.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logging()


# ============================================================================
# FILE STABILIZATION
# ============================================================================

def wait_for_file_stability(filepath, check_interval=FILE_STABILITY_CHECK_INTERVAL,
                            stability_threshold=FILE_STABILITY_THRESHOLD):
    """
    Wait until file size remains unchanged for the stability threshold.
    
    This ensures OneDrive has completely synced the file before reading.
    
    Args:
        filepath: Path to the file to monitor
        check_interval: How often to check file size (seconds)
        stability_threshold: How long size must remain unchanged (seconds)
    
    Returns:
        True if file stabilized, False if file disappeared
    """
    logger.info(f"Waiting for file stability: {filepath}")
    
    try:
        last_size = -1
        stable_since = None
        
        while True:
            if not os.path.exists(filepath):
                logger.warning(f"File disappeared during stabilization check: {filepath}")
                return False
            
            current_size = os.path.getsize(filepath)
            
            if current_size == last_size:
                # Size unchanged
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= stability_threshold:
                    logger.info(f"File stabilized at {current_size} bytes: {filepath}")
                    return True
            else:
                # Size changed, reset stability timer
                logger.debug(f"File size changed: {last_size} -> {current_size} bytes")
                last_size = current_size
                stable_since = None
            
            time.sleep(check_interval)
    
    except Exception as e:
        logger.error(f"Error during file stabilization check: {e}", exc_info=True)
        return False


# ============================================================================
# OLLAMA INTEGRATION
# ============================================================================

def summarize_with_ollama(text):
    """
    Summarize alert text using Ollama with the specified system prompt.
    
    Args:
        text: Raw alert text to summarize
    
    Returns:
        Summarized text as Markdown, or None on error
    """
    try:
        logger.info(f"Sending text to Ollama (model: {OLLAMA_MODEL}, {len(text)} chars)")
        
        # Configure Ollama client
        client = ollama.Client(host=OLLAMA_BASE_URL)
        
        # Generate summary
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    'role': 'system',
                    'content': SYSTEM_PROMPT
                },
                {
                    'role': 'user',
                    'content': text
                }
            ]
        )
        
        summary = response['message']['content'].strip()
        logger.info(f"Ollama summary generated ({len(summary)} chars)")
        logger.debug(f"Summary preview: {summary[:200]}...")
        
        return summary
    
    except Exception as e:
        logger.error(f"Error during Ollama summarization: {e}", exc_info=True)
        return None


# ============================================================================
# TEAMS WEBHOOK INTEGRATION
# ============================================================================

def send_to_teams(summary, max_retries=WEBHOOK_MAX_RETRIES, retry_delays=WEBHOOK_RETRY_DELAYS):
    """
    Post summary to Microsoft Teams via incoming webhook with retry logic.
    
    Args:
        summary: Markdown summary to post
        max_retries: Maximum number of retry attempts
        retry_delays: List of delay durations for each retry (seconds)
    
    Returns:
        True if successful, False if all retries failed
    """
    if not TEAMS_WEBHOOK_URL:
        logger.error("TEAMS_WEBHOOK_URL not configured in .env")
        return False
    
    # Teams webhook payload format (Office 365 Message Card)
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "FF0000",
        "summary": "Datadog Alert",
        "sections": [
            {
                "text": summary
            }
        ]
    }
    
    for attempt in range(max_retries):
        try:
            logger.info(f"Posting to Teams (attempt {attempt + 1}/{max_retries})")
            
            response = requests.post(
                TEAMS_WEBHOOK_URL,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("Successfully posted to Teams")
                return True
            else:
                logger.warning(f"Teams webhook returned status {response.status_code}: {response.text}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error posting to Teams: {e}")
        
        # Retry with exponential backoff (if not last attempt)
        if attempt < max_retries - 1:
            delay = retry_delays[attempt] if attempt < len(retry_delays) else retry_delays[-1]
            logger.info(f"Retrying in {delay} seconds...")
            time.sleep(delay)
    
    logger.error(f"Failed to post to Teams after {max_retries} attempts")
    return False


# ============================================================================
# FILE ARCHIVING
# ============================================================================

def archive_file(filepath, success=True):
    """
    Move processed file to archive/ or failed/ subfolder.
    
    If a file with the same name exists, append timestamp to avoid collision.
    
    Args:
        filepath: Path to the file to archive
        success: True to move to archive/, False to move to failed/
    
    Returns:
        True if successful, False on error
    """
    try:
        file_path = Path(filepath)
        
        if not file_path.exists():
            logger.warning(f"Cannot archive non-existent file: {filepath}")
            return False
        
        # Determine target folder
        target_folder = file_path.parent / ('archive' if success else 'failed')
        target_folder.mkdir(exist_ok=True)
        
        # Determine target filename
        target_file = target_folder / file_path.name
        
        # Handle collision by appending timestamp
        if target_file.exists():
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            stem = file_path.stem
            suffix = file_path.suffix
            target_file = target_folder / f"{stem}_{timestamp}{suffix}"
            logger.info(f"Collision detected, using timestamped name: {target_file.name}")
        
        # Move file
        file_path.rename(target_file)
        logger.info(f"Archived to {'archive' if success else 'failed'}: {target_file}")
        
        return True
    
    except Exception as e:
        logger.error(f"Error archiving file {filepath}: {e}", exc_info=True)
        return False


# ============================================================================
# WATCHDOG EVENT HANDLER
# ============================================================================

class DatadogAlertHandler(FileSystemEventHandler):
    """Handle file system events for Datadog alert .txt files."""
    
    def on_created(self, event):
        """Handle new file creation events."""
        if event.is_directory:
            return
        
        # Only process .txt files
        if not event.src_path.endswith('.txt'):
            logger.debug(f"Ignoring non-.txt file: {event.src_path}")
            return
        
        # Skip files in archive/ and failed/ subdirectories
        path = Path(event.src_path)
        if path.parent.name in ('archive', 'failed'):
            logger.debug(f"Ignoring file in {path.parent.name}/: {event.src_path}")
            return
        
        logger.info(f"New alert file detected: {event.src_path}")
        self.process_alert_file(event.src_path)
    
    def process_alert_file(self, filepath):
        """
        Complete processing pipeline for a new alert file.
        
        Pipeline:
        1. Wait for file stability (OneDrive sync completion)
        2. Read file content
        3. Summarize with Ollama
        4. Post to Teams (with retry)
        5. Archive file (to archive/ or failed/ based on webhook success)
        """
        try:
            # Step 1: Wait for file to stabilize
            if not wait_for_file_stability(filepath):
                logger.error(f"File stability check failed: {filepath}")
                return
            
            # Step 2: Read file content
            logger.info(f"Reading alert file: {filepath}")
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    alert_text = f.read()
                logger.info(f"Read {len(alert_text)} characters from {filepath}")
            except Exception as e:
                logger.error(f"Error reading file {filepath}: {e}", exc_info=True)
                return
            
            # Step 3: Summarize with Ollama
            summary = summarize_with_ollama(alert_text)
            if not summary:
                logger.error(f"Failed to generate summary for {filepath}")
                archive_file(filepath, success=False)
                return
            
            # Print summary to console
            print("\n" + "="*80)
            print("ALERT SUMMARY")
            print("="*80)
            print(summary)
            print("="*80 + "\n")
            
            # Step 4: Post to Teams
            teams_success = send_to_teams(summary)
            
            # Step 5: Archive file
            archive_file(filepath, success=teams_success)
            
            if teams_success:
                logger.info(f"Successfully processed alert: {filepath}")
            else:
                logger.warning(f"Processed alert but Teams posting failed: {filepath}")
        
        except Exception as e:
            logger.error(f"Unexpected error processing {filepath}: {e}", exc_info=True)
            archive_file(filepath, success=False)


# ============================================================================
# STARTUP VALIDATION
# ============================================================================

def validate_startup():
    """
    Validate environment and dependencies before starting the agent.
    
    Returns:
        True if all checks pass, False otherwise
    """
    logger.info("Running startup validation checks...")
    
    # Check if .env is loaded
    if not TEAMS_WEBHOOK_URL:
        logger.error("TEAMS_WEBHOOK_URL not set in .env file")
        logger.error("Please copy .env.example to .env and configure it")
        return False
    
    # Check if watch directory exists
    watch_path = Path(WATCH_DIR)
    if not watch_path.exists():
        logger.error(f"Watch directory does not exist: {WATCH_DIR}")
        logger.error("Please create the directory or update WATCH_DIR in .env")
        return False
    
    if not watch_path.is_dir():
        logger.error(f"Watch path is not a directory: {WATCH_DIR}")
        return False
    
    logger.info(f"Watch directory OK: {WATCH_DIR}")
    
    # Check Ollama connectivity
    try:
        logger.info(f"Testing Ollama connection at {OLLAMA_BASE_URL}...")
        client = ollama.Client(host=OLLAMA_BASE_URL)
        
        # List models to verify connection
        models = client.list()
        logger.info(f"Ollama connection OK ({len(models.get('models', []))} models available)")
        
        # Check if specified model exists
        model_names = [m['name'] for m in models.get('models', [])]
        if not any(OLLAMA_MODEL in name for name in model_names):
            logger.warning(f"Model '{OLLAMA_MODEL}' not found in Ollama")
            logger.warning(f"Available models: {', '.join(model_names)}")
            logger.warning("Ollama will attempt to pull the model on first use")
    
    except Exception as e:
        logger.error(f"Failed to connect to Ollama at {OLLAMA_BASE_URL}")
        logger.error(f"Error: {e}")
        logger.error("Please ensure Ollama is running: ollama serve")
        return False
    
    logger.info("All startup validation checks passed ✓")
    return True


# ============================================================================
# MAIN FUNCTION & SIGNAL HANDLING
# ============================================================================

# Global observer for graceful shutdown
observer = None
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals (SIGINT, SIGTERM) gracefully."""
    global shutdown_requested
    
    signal_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    
    shutdown_requested = True
    
    if observer:
        observer.stop()


def main():
    """Main entry point for the Datadog alert monitoring agent."""
    global observer
    
    logger.info("="*80)
    logger.info("Datadog Alert Monitoring Agent with Ollama Summarization")
    logger.info("="*80)
    logger.info(f"Configuration:")
    logger.info(f"  Watch Directory: {WATCH_DIR}")
    logger.info(f"  Ollama Model: {OLLAMA_MODEL}")
    logger.info(f"  Ollama Base URL: {OLLAMA_BASE_URL}")
    logger.info(f"  Teams Webhook: {'configured' if TEAMS_WEBHOOK_URL else 'NOT CONFIGURED'}")
    logger.info("="*80)
    
    # Run startup validation
    if not validate_startup():
        logger.error("Startup validation failed. Exiting.")
        sys.exit(1)
    
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and configure watchdog observer
    event_handler = DatadogAlertHandler()
    observer = Observer()
    observer.schedule(event_handler, WATCH_DIR, recursive=False)
    
    # Start monitoring
    observer.start()
    logger.info(f"Started monitoring: {WATCH_DIR}")
    logger.info("Press Ctrl+C to stop")
    
    try:
        # Keep running until shutdown signal received
        while not shutdown_requested:
            time.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    
    finally:
        # Clean shutdown
        logger.info("Stopping observer...")
        observer.stop()
        observer.join()
        logger.info("Agent stopped gracefully")


if __name__ == '__main__':
    main()
