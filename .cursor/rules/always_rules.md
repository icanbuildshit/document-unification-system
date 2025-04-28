# Always Rules for Document Unification System

## Orchestration Architecture
- Use specialized orchestrators for each major system component
- Follow hierarchical orchestration model with clear delegation
- Implement graceful failure handling in all orchestrators
- Design orchestrators for both scalability and resilience
- Document all orchestrator interfaces and responsibilities

## Code Style and Structure
- Follow PEP 8 style guidelines for Python code
- Use type hints for all function parameters and return values
- Document all classes and functions with docstrings
- Organize imports alphabetically within their groups
- Use asynchronous programming where appropriate for I/O operations

## Security Practices
- Validate all user inputs before processing
- Use environment variables for configuration and secrets
- Implement comprehensive error handling
- Never expose sensitive data in logs or error messages
- Sanitize all output to prevent injection attacks
- Follow zero-trust orchestration principles for internal components

## Document Processing
- Preserve document structure during parsing
- Handle edge cases like empty documents, corrupt files
- Maintain provenance tracking for all extracted data
- Implement conflict resolution with explicit reasoning
- Document all transformations in audit trail

## Orchestration Logging
- Log all orchestrator decisions and handoffs
- Include sufficient context in logs for debugging
- Use structured logging format for machine readability
- Preserve log durability for compliance purposes
- Include orchestrator ID in all log entries

## Testing and Quality
- Write unit tests for all critical functions
- Include integration tests for agent interactions
- Validate document outputs against source materials
- Log all errors and warnings with appropriate context
- Include clear user feedback for processing failures
- Test orchestrator failure modes and recovery procedures

## Interoperability
- Use standard data formats for agent communication
- Design for multi-environment deployment
- Support standard input and output formats
- Implement well-defined APIs between components
- Document all integration points for external systems 