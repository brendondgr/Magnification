
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[3]))

# Mock logging to avoid noise
import logging
logging.basicConfig(level=logging.INFO)

from utils.backend.scrapers.scraping_service import execute_full_scraping_workflow
import json

def test_workflow_config_loading():
    print("Testing workflow configuration loading...")
    
    # We want to check if it logs the correct sites
    # Since we can't easily capture the scraper call without complex mocking,
    # we'll look at the 'results' return value which contains the config used.
    
    # Run with search_terms=None to trigger config loading
    # We'll mock the internal scraper to not actually run if possible, 
    # but for simplicity, let's just see if we can get past Step 1.
    
    try:
        # We pass search_terms=None but we'll likely hit an error in Step 2 
        # because we don't want to actually scrape.
        # However, Step 1 sets 'results['steps']['config']'.
        
        results = execute_full_scraping_workflow(
            search_terms=None,
            save_to_database=False # Don't touch DB
        )
    except Exception as e:
        # If it fails after Step 1, we might still have the results object if we return it
        print(f"Workflow stopped (expectedly): {e}")

    # Read the config file to compare
    config_path = Path(__file__).resolve().parents[3] / "config" / "jobs_config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    print(f"Config Sites: {config.get('sites')}")
    print(f"Config Results Wanted: {config.get('results_wanted')}")
    print(f"Config Hours Old: {config.get('hours_old')}")

if __name__ == "__main__":
    test_workflow_config_loading()
