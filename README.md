# Document Unification System

A sophisticated system for processing and unifying technical documents using a specialized orchestrator architecture with advanced security and compliance features.

## Features

- **Intelligent Document Processing**: Extract structured content from PDF, DOCX, HTML, PPTX, and other formats with layout preservation
- **Advanced Chunking**: Hybrid spatial-semantic chunking that respects document layout and content relationships
- **Secure JWT Authentication**: RS256 signed tokens with refresh rotation and step-up MFA
- **Comprehensive Audit Logging**: Immutable, cryptographically signed audit trail for compliance
- **Orchestrated Architecture**: Modular, specialized orchestrators for better scalability and fault isolation
- **Robust Error Handling**: Graceful fallbacks and standardized error patterns
- **Storage Abstraction**: Flexible backend storage (database, file-based) with encryption options
- **Batch Processing**: Process multiple documents with parallel execution options
- **LangChain Integration**: Compatible with LangChain's document processing pipelines

## Specialized Orchestration Architecture

This system implements a modular, specialized orchestration architecture where each major component has its own dedicated orchestrator. This design enables better scaling, fault isolation, and component specialization.

### Orchestrator Hierarchy

- **Master Orchestrator**: Coordinates the entire system, delegates to specialized orchestrators, and maintains global state
- **Document Parser Orchestrator**: Manages document parsing across different formats and extraction strategies
- **Metadata Management Orchestrator**: Handles metadata extraction, validation, and privacy concerns
- **Storage Orchestrator**: Coordinates document persistence, retrieval, and backup operations
- **Workflow Orchestrator**: Manages multi-step document processing workflows
- **Authentication Orchestrator**: Handles user identity, access control, and token management
- **Audit Orchestrator**: Ensures regulatory compliance and maintains audit logs
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

## Security Features

The Document Unification System includes comprehensive security features designed for enterprise use:

### Authentication & Authorization

- **JWT-based Authentication**: RS256 signed tokens with configurable expiration
- **Refresh Token Rotation**: Refresh tokens are rotated on use for enhanced security
- **Step-up MFA**: Risk-based MFA using behavioral and contextual signals
- **Hierarchical Access Control**: Fine-grained permissions for documents and resources

### Audit & Compliance

- **Immutable Audit Trail**: Cryptographically signed audit logs for non-repudiation
- **PII/PHI Masking**: Automatic redaction of sensitive information in logs
- **Comprehensive Event Tracking**: All actions are logged with context and rationale
- **GDPR/HIPAA/GLBA Compliance**: Built-in compliance features for major regulations

### Data Protection

- **Secure Storage**: Encryption options for sensitive document data
- **Minimal Data Collection**: Configurable metadata scrubbing for privacy
- **Pseudonymization**: Options for pseudonymizing user identifiers
- **Fine-grained Retention**: Customizable data retention policies

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager
- Virtual environment (recommended)
- Redis (for session management)
- PostgreSQL or Supabase (optional, for database storage)

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/icanbuildshit/document-unification-system.git
   cd document-unification-system
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

4. Set up environment variables:
   ```bash
   cp .env.example .env  # Then edit .env with your specific settings
   ```

5. Initialize the database (if using database storage):
   ```bash
   python setup_db.py
   ```

## Usage

### Basic Usage

Process a single document:

```bash
python main.py path/to/document.pdf
```

### Batch Processing

Process multiple documents at once:

```bash
python main.py --batch path/to/document/directory
```

Or process documents listed in a file:

```bash
python main.py --batch path/to/document_list.txt
```

### Advanced Options

The system supports numerous advanced options for document processing:

```bash
# Enable metadata scrubbing
python main.py --scrub-metadata --scrub-fields author,creator --scrub-mode redact path/to/document.pdf

# Extract tables and perform OCR
python main.py --extract-tables --perform-ocr path/to/document.pdf

# Specify output directory
python main.py --output-dir /path/to/output path/to/document.pdf

# Use authentication
python main.py --require-auth --user-id john.doe@example.com path/to/document.pdf

# Use legacy flow (non-orchestrated)
python main.py --use-legacy-flow path/to/document.pdf

# Specify audit level
python main.py --audit-level comprehensive path/to/document.pdf
```

### Configuration File

You can also specify options in a YAML or JSON configuration file:

```bash
python main.py --config path/to/config.yaml
```

Example config.yaml:
```yaml
processing_options:
  extract_tables: true
  extract_images: true
  perform_ocr: true
  scrub_metadata: true
  scrub_fields: ["author", "creator", "custom"]
  scrub_mode: "redact"
  audit_trail_level: "comprehensive"
  persist_to_database: true
  encrypt_sensitive_data: true
```

## Project Structure

```
document-unification-system/
├── data/                # Data directories
│   ├── input/           # Input documents
│   ├── intermediate/    # Intermediate processing results
│   └── output/          # Final output
├── logs/                # Log files
├── prompts/             # System prompts for agents
├── src/                 # Source code
│   ├── agents/          # Agent and orchestrator implementations
│   │   ├── auth_agent.py                # Authentication agent
│   │   ├── chunking.py                  # Document chunking
│   │   ├── document_parser_orchestrator.py # Document parsing orchestrator
│   │   ├── orchestrator.py              # Master orchestrator
│   │   ├── parser_agent.py              # Document parsing agent
│   │   └── ...
│   ├── storage/         # Storage implementations
│   └── utils/           # Utility functions
│       ├── orchestrator_communication.py # Communication protocol
│       ├── orchestrator_fallback.py      # Error handling
│       ├── orchestrator_logging.py       # Logging utilities
│       └── ...
├── tests/               # Test suite
├── .env.example         # Example environment variables
├── main.py              # Main entry point
├── ROADMAP.md           # Development roadmap
└── requirements.txt     # Python dependencies
```

## Token & Credential Best Practices

The system follows these best practices for token and credential management:

- **Strong Signing & Encryption**: RS256 for JWT signing; encryption for sensitive claims
- **Short-Lived Access Tokens**: Default 15-minute expiration for access tokens
- **Refresh Token Rotation**: Refresh tokens are rotated on every use
- **Audience/Issuer Validation**: Strict validation of token claims
- **No Sensitive Data in JWTs**: Minimal claims in token payloads
- **Secure Storage**: Tokens stored in Redis with TTL matching token expiry

## Development and Extension

### Adding a New Orchestrator

To add a new specialized orchestrator:

1. Create a new file in `src/agents/` (e.g., `new_orchestrator.py`)
2. Implement the orchestrator class with a `handle_message` method
3. Register message handlers for different message types
4. Update the `MessageType` enum in `src/utils/orchestrator_communication.py`
5. Add the new orchestrator to the master orchestrator's initialization

### Adding a New Document Format

To add support for a new document format:

1. Implement a parser for the format in `parser_agent.py`
2. Register the format in the supported formats list
3. Add appropriate tests in the test suite

## Roadmap & Project Status

See [ROADMAP.md](./ROADMAP.md) for a list of completed features, current TODOs, and future plans.

## Audit Logging & Compliance

All actions in the system are logged to provide a comprehensive audit trail. The audit log includes:

- Timestamp with ISO-8601 format and UTC timezone
- Action performed (e.g., document parsing, token issuance)
- Actor (user or system component) performing the action
- Target of the action (e.g., document ID, resource path)
- Result of the action (success, error)
- Rationale or context for the action
- Additional metadata (filtered for sensitive information)

Logs are stored in JSONL format with cryptographic signatures to ensure integrity.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit a pull request.

1. Fork the repository
2. Create your feature branch: `git checkout -b feature/amazing-feature`
3. Commit your changes: `git commit -m 'Add some amazing feature'`
4. Push to the branch: `git push origin feature/amazing-feature`
5. Open a pull request

## Acknowledgments

- This project integrates with LangChain for document processing
- Authentication system follows OAuth 2.1 and JWT best practices
- Audit logging is inspired by NIST SP 800-92 guidelines