# Specialized Orchestrator Rules

## Core Principles for All Orchestrators
- Break tasks into modular, atomic components
- Maintain comprehensive logs of all actions and handoffs
- Follow single responsibility principle
- Handle failures gracefully with appropriate recovery mechanisms
- Respect security and privacy boundaries

## Master Orchestrator
- Coordinate between specialized orchestrators
- Maintain global system state
- Allocate resources and prioritize tasks
- Report system-wide status and metrics
- Enforce global security and compliance policies

## Document Parser Orchestrator
- Split parsing tasks by document type and format
- Route documents to specialized parsing agents
- Maintain document integrity and structure
- Track parsing errors and anomalies
- Handle multi-format document processing workflows

## Metadata Management Orchestrator
- Coordinate metadata extraction, validation, and enrichment
- Manage scrubbing operations for sensitive metadata
- Enforce metadata schema validation
- Track metadata lineage and transformations
- Handle privacy and compliance requirements for metadata

## Storage Orchestrator
- Manage document persistence across storage backends
- Handle chunking and retrieval operations
- Coordinate backup and recovery processes
- Maintain storage optimization strategies
- Enforce access controls for stored documents

## Authentication Orchestrator
- Manage user identity and access verification
- Coordinate token issuance, refreshing, and revocation
- Handle session state management
- Enforce multi-factor authentication rules
- Maintain authentication audit logs

## Workflow Orchestrator
- Manage task queues and priorities
- Coordinate complex multi-stage document workflows
- Track workflow state and handle resumption
- Manage timeouts and retry policies
- Provide workflow visualization and debugging

## Audit & Compliance Orchestrator
- Collect and consolidate audit logs from all agents
- Enforce regulatory compliance checks
- Generate compliance reports and attestations
- Track data handling for privacy regulations
- Manage data retention and deletion policies

## Analytics Orchestrator
- Coordinate data collection for performance metrics
- Manage system utilization and bottleneck detection
- Track document processing statistics
- Generate operational insights and recommendations
- Handle batch analytics processing

## Publication Orchestrator
- Coordinate document output format generation
- Manage template application and styling
- Handle document versioning and distribution
- Enforce output validation rules
- Track publication states and history 