# Agent-Specific Rules

## Agent Orchestration Patterns
- Agents must communicate through structured message formats
- Each agent should report status and errors to its specialized orchestrator
- Use idempotent operations when possible for retry reliability
- Implement graceful degradation for service disruptions
- Support both synchronous and asynchronous operation modes

## Parser Agent
- Use layout-aware parsing for all document formats
- Extract structural elements (headings, tables, lists)
- Preserve metadata like formatting and positions
- Handle embedded images and diagrams where possible
- Detect language and encoding automatically
- Report to Document Parser Orchestrator

## Validator Agent
- Cross-reference facts between documents using semantic matching
- Calculate confidence scores for potential contradictions
- Maintain provenance for all identified facts
- Use entity recognition to extract structured data
- Consider document recency and authority in validation
- Report to Workflow Orchestrator

## Conflict Resolver Agent
- Apply resolution hierarchy consistently
- Document reasoning for all resolution decisions
- Flag low-confidence resolutions for human review
- Handle edge cases and special content types
- Preserve original contradictory statements in metadata
- Report to Workflow Orchestrator

## Publisher Agent
- Generate semantically correct output formats
- Include comprehensive metadata in outputs
- Create accessible and well-structured documents
- Implement consistent styling and formatting
- Preserve document hierarchy in all output formats
- Report to Publication Orchestrator

## Authentication Agent
- Validate user credentials according to security policy
- Handle token generation and validation
- Manage multi-factor authentication challenges
- Support federated authentication providers
- Log all authentication attempts
- Report to Authentication Orchestrator

## Storage Agent
- Persist documents in configured storage backends
- Manage chunking and retrieval operations
- Implement read/write access controls
- Handle storage errors and retries
- Support multiple storage providers
- Report to Storage Orchestrator

## Audit Agent
- Record all system actions in immutable logs
- Implement tamper-evident logging
- Support compliance reporting formats
- Mask sensitive data in logs according to policy
- Provide log querying and filtering capabilities
- Report to Audit & Compliance Orchestrator

## Analytics Agent
- Collect performance metrics across system components
- Generate usage and performance reports
- Detect anomalies in system behavior
- Track resource utilization
- Provide insights for system optimization
- Report to Analytics Orchestrator 