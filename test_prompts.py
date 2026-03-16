#!/usr/bin/env python3
"""
Test script to review Ollama LLM output against actual Datadog alert files.

This script:
1. Reads all .txt files from the OneDrive datadog-alert-emails folder
2. Feeds them to Ollama with the current system prompt
3. Displays the generated summaries for review
4. Does NOT post to Teams (safe for iteration)

Usage:
    python test_prompts.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import ollama

# Load environment variables
load_dotenv()

WATCH_DIR = os.path.expanduser(os.getenv('WATCH_DIR', '~/OneDrive - Visionet/Datadog_Alerts'))
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.1:8b')
OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')

# System prompt from agent.py
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


def test_file(filepath):
    """
    Test a single alert file through the Ollama pipeline.
    
    Args:
        filepath: Path to the .txt file
    
    Returns:
        Dictionary with file info and summary, or None on error
    """
    try:
        # Read file
        with open(filepath, 'r', encoding='utf-8') as f:
            alert_text = f.read()
        
        # Generate summary
        client = ollama.Client(host=OLLAMA_BASE_URL)
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    'role': 'system',
                    'content': SYSTEM_PROMPT
                },
                {
                    'role': 'user',
                    'content': alert_text
                }
            ]
        )
        
        summary = response['message']['content'].strip()
        
        return {
            'filename': os.path.basename(filepath),
            'filepath': filepath,
            'alert_text_length': len(alert_text),
            'summary': summary,
            'summary_length': len(summary),
            'error': None
        }
    
    except Exception as e:
        return {
            'filename': os.path.basename(filepath),
            'filepath': filepath,
            'alert_text_length': 0,
            'summary': None,
            'summary_length': 0,
            'error': str(e)
        }


def main():
    """Main entry point for testing."""
    watch_path = Path(WATCH_DIR)
    
    # Validate directory
    if not watch_path.exists():
        print(f"❌ Error: Watch directory does not exist: {WATCH_DIR}")
        sys.exit(1)
    
    if not watch_path.is_dir():
        print(f"❌ Error: Watch path is not a directory: {WATCH_DIR}")
        sys.exit(1)
    
    # Find all .txt files in the main directory (not in subdirs)
    txt_files = sorted([f for f in watch_path.glob('*.txt') if f.is_file()])
    
    if not txt_files:
        print(f"⚠️  No .txt files found in: {WATCH_DIR}")
        sys.exit(0)
    
    print("="*80)
    print("DATADOG ALERT PROMPT TEST")
    print("="*80)
    print(f"Watch Directory: {WATCH_DIR}")
    print(f"Ollama Model: {OLLAMA_MODEL}")
    print(f"Files to Test: {len(txt_files)}")
    print("="*80)
    print()
    
    # Test each file
    results = []
    for idx, filepath in enumerate(txt_files, 1):
        print(f"\n[{idx}/{len(txt_files)}] Testing: {filepath.name}")
        print("-" * 80)
        
        result = test_file(filepath)
        results.append(result)
        
        if result['error']:
            print(f"❌ ERROR: {result['error']}")
        else:
            print(f"✅ Alert text: {result['alert_text_length']} chars")
            print(f"✅ Summary: {result['summary_length']} chars")
            print()
            print("GENERATED SUMMARY:")
            print("-" * 80)
            print(result['summary'])
            print("-" * 80)
    
    # Summary statistics
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    successful = sum(1 for r in results if not r['error'])
    failed = sum(1 for r in results if r['error'])
    
    print(f"✅ Successful: {successful}/{len(results)}")
    print(f"❌ Failed: {failed}/{len(results)}")
    
    if failed > 0:
        print("\nFailed files:")
        for result in results:
            if result['error']:
                print(f"  • {result['filename']}: {result['error']}")
    
    print("="*80)
    print("\n💡 NEXT STEPS:")
    print("1. Review the summaries above")
    print("2. Identify issues with the system prompt")
    print("3. Edit SYSTEM_PROMPT in this file or agent.py")
    print("4. Re-run: python test_prompts.py")
    print("5. Once satisfied, restart the agent with: python agent.py")
    print()


if __name__ == '__main__':
    main()
