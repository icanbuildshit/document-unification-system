"""
Main pipeline for Document Unification System.
"""

import argparse
import asyncio
import json
import os
from src.agents.orchestrator import OrchestratorAgent

try:
    import yaml
except ImportError:
    yaml = None

def load_config(config_path):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    ext = os.path.splitext(config_path)[1].lower()
    with open(config_path, 'r', encoding='utf-8') as f:
        if ext in ['.yaml', '.yml']:
            if not yaml:
                raise ImportError("PyYAML is not installed. Install with 'pip install pyyaml'.")
            return yaml.safe_load(f)
        elif ext == '.json':
            return json.load(f)
        else:
            raise ValueError(f"Unsupported config file format: {ext}")

def log_action(action, target, result, rationale, extra=None):
    from datetime import datetime
    log_entry = (
        f"[{datetime.utcnow().isoformat()}Z] ACTION: \"{action}\"\n"
        f"TARGET: \"{target}\"\n"
        f"RESULT: \"{result}\"\n"
        f"RATIONALE: \"{rationale}\"\n"
        f"EXTRA: {extra}\n"
    )
    log_path = "output/audit/audit_trail.jsonl"
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")

def main():
    """
    Orchestrate document parsing, chunking, keyword extraction, and storage using OrchestratorAgent.
    """
    parser = argparse.ArgumentParser(description="Document Unification System")
    parser.add_argument("file_path", type=str, help="Path to the input document")
    parser.add_argument("--document_id", type=str, default=None, help="Optional document ID")
    parser.add_argument("--scrub-metadata", action="store_true", help="Enable metadata scrubbing on document metadata.")
    parser.add_argument("--scrub-fields", type=str, default=None, help="Comma-separated list of metadata fields to scrub (e.g. 'author,created').")
    parser.add_argument("--scrub-mode", type=str, choices=["redact", "remove", "none"], default="redact", help="How to scrub metadata fields: redact, remove, or none.")
    parser.add_argument("--config", type=str, default=None, help="Path to config file (YAML or JSON)")
    args = parser.parse_args()

    config = {}
    if args.config:
        try:
            config = load_config(args.config)
            log_action(
                action="load_config",
                target=args.config,
                result="success",
                rationale="Loaded configuration file for pipeline run.",
                extra=None
            )
        except Exception as e:
            log_action(
                action="load_config",
                target=args.config,
                result="error",
                rationale=f"Failed to load config: {e}",
                extra=None
            )
            raise

    # Merge CLI args (priority) with config file
    merged = config.copy() if config else {}
    merged['file_path'] = args.file_path or config.get('file_path')
    merged['document_id'] = args.document_id or config.get('document_id')
    merged['scrub_metadata'] = args.scrub_metadata if args.scrub_metadata else config.get('scrub_metadata', False)
    merged['scrub_fields'] = [f.strip() for f in args.scrub_fields.split(",")] if args.scrub_fields else config.get('scrub_fields')
    merged['scrub_mode'] = args.scrub_mode or config.get('scrub_mode', 'redact')

    scrub_fields = merged['scrub_fields']

    orchestrator = OrchestratorAgent(
        scrub_metadata=merged['scrub_metadata'],
        scrub_fields=scrub_fields,
        scrub_mode=merged['scrub_mode']
    )
    result = asyncio.run(orchestrator.process_document(merged['file_path'], merged['document_id']))
    print("Processing summary:", result)

if __name__ == "__main__":
    main() 