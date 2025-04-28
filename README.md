# Multi-Agent Document Unification System

A sophisticated system for unifying multiple technical documents into a comprehensive, coherent document suite using specialized AI agents.

## Features

- **Intelligent Parsing**: Extract content from PDF, DOCX, HTML, and other formats with layout preservation
- **Conflict Detection & Resolution**: Automatically identify and resolve contradictions across documents
- **Terminology Standardization**: Enforce consistent terminology and generate comprehensive glossaries
- **Smart Structure**: Organize content following the Divio documentation framework (Tutorials, How-To's, Reference, Explanations)
- **Compliance Integration**: Ensure documentation adheres to standards like ISO 9001 and ISO 27001
- **Multi-Format Publishing**: Generate output in MediaWiki, PDF, HTML, and JSON formats
- **Audit Trail**: Maintain comprehensive logs of all transformations for accountability

## Specialized Orchestration Architecture

This system implements a modular, specialized orchestration architecture where each major component has its own dedicated orchestrator. This design enables better scaling, fault isolation, and component specialization.

### Orchestrator Hierarchy

- **Master Orchestrator**: Coordinates the entire system, delegates to specialized orchestrators, and maintains global state
- **Document Parser Orchestrator**: Manages document parsing across different formats and extraction strategies
- **Metadata Management Orchestrator**: Handles metadata extraction, validation, and privacy concerns
- **Storage Orchestrator**: Coordinates document persistence, retrieval, and backup operations
- **Workflow Orchestrator**: Manages multi-step document processing workflows
- **Authentication Orchestrator**: Handles user identity, access control, and token management
- **Audit & Compliance Orchestrator**: Ensures regulatory compliance and maintains audit logs
- **Analytics Orchestrator**: Collects performance metrics and generates operational insights
- **Publication Orchestrator**: Manages output generation in various formats

### Benefits of Specialized Orchestration

- **Modularity**: Each orchestrator focuses on a specific domain, making the system easier to maintain and extend
- **Fault Isolation**: Failures in one component don't cascade to the entire system
- **Scalability**: Components can scale independently based on workload
- **Specialization**: Each orchestrator implements domain-specific optimization strategies
- **Clear Boundaries**: Well-defined interfaces between components improve security and testability

### Orchestrator Communication

Orchestrators communicate through a standardized message protocol that includes request IDs, context information, and structured payloads. All orchestrator interactions are logged for audit and debugging purposes.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager
- Virtual environment (recommended)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/doc-unification-system.git
   cd doc-unification-system
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Download required NLP models:
   ```bash
   python -m spacy download en_core_web_sm
   ```

5. Set up environment variables:
   ```bash
   cp .env.example .env  # Then edit .env with your specific settings
   ```

## Environment Variables (Supabase Setup)

To enable Supabase storage, you must provide your Supabase project credentials as environment variables. For security, the real `.env` file is git-ignored and hidden from AI, but `.env.example` is provided as a schema for teammates and AI agents.

1. Copy `.env.example` to `.env` in your project root:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and fill in your real Supabase credentials:
   ```env
   SUPABASE_URL=your-supabase-project-url
   SUPABASE_KEY=your-supabase-service-role-key
   ```
3. **Never commit `.env` to version control.**

If you do not see `.env` in your editor, check your workspace settings for `files.exclude` or `search.exclude` rules.

## Usage

### Basic Usage

Run the system with input documents:

```bash
python main.py path/to/document1.pdf
```

### Using Configuration File (YAML or JSON)

You can specify pipeline options in a config file (YAML or JSON):

```bash
python main.py --config path/to/config.yaml
```

or

```bash
python main.py --config path/to/config.json
```

**Note:** CLI arguments always take precedence over config file values.

#### Example config.yaml
```yaml
file_path: path/to/document1.pdf
document_id: mydoc123
scrub_metadata: true
scrub_fields:
  - author
  - created
scrub_mode: redact
```

#### Example config.json
```json
{
  "file_path": "path/to/document1.pdf",
  "document_id": "mydoc123",
  "scrub_metadata": true,
  "scrub_fields": ["author", "created"],
  "scrub_mode": "redact"
}
```

### Specifying Output Directory

```bash
python main.py --output path/to/output/dir path/to/document1.pdf path/to/document2.docx
```

## Configuration

The system can be configured using a JSON configuration file. See `config/config.json` for a sample configuration.

Key configuration areas include:

- Document parsing settings
- Conflict resolution strategies
- Taxonomy and terminology preferences
- Documentation framework options
- Compliance standards
- Output formats

## Project Structure

```
doc-unification-system/
├── config/              # Configuration files
├── data/                # Data directories
│   ├── input/           # Input documents
│   ├── intermediate/    # Intermediate processing output
│   └── output/          # Final output
├── logs/                # Log files
├── src/                 # Source code
│   ├── agents/          # Agent implementations
│   ├── utils/           # Utility functions
│   └── workflows/       # Workflow orchestration
├── templates/           # Output templates
├── .env                 # Environment variables
├── main.py              # Main entry point
└── requirements.txt     # Python dependencies
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Multi-Agent Orchestration Architecture

### Overview
This system uses a modular, multi-agent architecture to unify document processing tasks. Each agent is responsible for a specific function, coordinated by an OrchestratorAgent. This design enables scalability, testability, and easy extension to distributed or event-driven workflows.

### Agent Roles
- **OrchestratorAgent**: Coordinates the workflow and delegates tasks to specialized agents.
- **ParsingAgent**: Handles document parsing (PDF, DOCX, HTML, etc.).
- **ChunkingAgent**: Performs hybrid spatial-semantic chunking of parsed elements.
- **KeywordAgent**: Extracts keywords from document chunks using NLP techniques.
- **StorageAgent**: Persists chunks and keywords to Supabase/PostgreSQL.

### Architecture Diagram
```
[OrchestratorAgent]
      |
      +---> [ParsingAgent] ---> [ChunkingAgent] ---> [KeywordAgent] ---> [StorageAgent]
```

### Message Protocol (for future event-driven workflows)
Agents can communicate using simple message envelopes:
```python
{
  "sender": "OrchestratorAgent",
  "recipient": "ChunkingAgent",
  "task": "chunk",
  "payload": { ... },
  "correlation_id": "uuid-1234"
}
```
This pattern allows easy migration to message queues or distributed systems.

### Best Practices
- **Single Responsibility**: Each agent should do one thing well.
- **Loose Coupling**: Use message envelopes or function calls for communication.
- **Extensibility**: Add new agents (e.g., for conflict resolution, graph building) without changing the orchestrator interface.
- **Testability**: Mock agents in tests to validate orchestration logic.
- **Observability**: Add logging and error handling in each agent for production use.

### Extending the System
- Add new agents for additional tasks (e.g., conflict detection, summarization).
- Replace in-memory calls with message queues for distributed processing.
- Integrate with monitoring and audit systems for compliance.

## Metadata Scrubbing & Audit Logging

This system supports flexible metadata scrubbing for privacy and compliance. You can control which metadata fields are scrubbed, and how, via CLI options:

```bash
python main.py path/to/document.pdf --scrub-metadata --scrub-fields author,created --scrub-mode redact
```

- `--scrub-metadata`: Enable metadata scrubbing
- `--scrub-fields`: Comma-separated list of fields to scrub (e.g., `author,created`)
- `--scrub-mode`: How to scrub fields: `redact` (replace with `REDACTED`), `remove` (delete field), or `none` (no action)

All metadata scrubbing events are logged to `output/audit/audit_trail.jsonl` for compliance and traceability.

## Roadmap & Project Status

See [ROADMAP.md](./ROADMAP.md) for a list of completed features, current TODOs, and future plans. 