<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" class="logo" width="120"/>

# Comprehensive Guide to Setting Up Claude Code for Agentic Coding

## Prerequisites and System Requirements

**Operating Systems**:
Claude Code officially supports macOS 10.15+, Ubuntu 20.04+/Debian 10+, and Windows via Windows Subsystem for Linux (WSL 2). Native Windows support is not available[^2][^8][^18].

**Hardware**:

- Minimum 4GB RAM (8GB+ recommended for complex workflows)
- 2GHz+ dual-core processor
- 500MB free disk space

**Software Dependencies**:

- Node.js 18+ (20.x recommended)
- npm 9+
- Git 2.23+
- Python 3.8+ (for certain MCP integrations)[^9]


## Step 1: Windows Subsystem for Linux (WSL) Setup

For Windows users:

```powershell
# PowerShell as Administrator
wsl --install -d Ubuntu-22.04
wsl --set-version Ubuntu-22.04 2
wsl --shutdown
```

**Post-Install Configuration**:

```bash
sudo apt update &amp;&amp; sudo apt upgrade -y
sudo apt install -y build-essential libssl-dev zlib1g-dev libbz2-dev \
libreadline-dev libsqlite3-dev curl llvm libncursesw5-dev xz-utils \
tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```


## Step 2: Node.js Environment Setup

**Recommended Installation via NVM**:

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc
nvm install 20.12.1
nvm use 20.12.1
```

**Verify Installation**:

```bash
node -v  # Should return v20.12.1
npm -v   # Should return 10.5.0+
which node  # Should show Linux path: /home/&lt;user&gt;/.nvm/versions/node/v20.12.1/bin/node
```


## Step 3: Claude Code Installation

**Global Installation**:

```bash
npm install -g @anthropic-ai/claude-code --force --no-os-check
```

**Post-Install Verification**:

```bash
claude --version  # Should return claude-code/0.12.7
claude doctor    # Runs system health check
```

**Troubleshooting Common Issues**:

```bash
# If encountering EACCES errors:
npm config set prefix ~/.npm-global
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' &gt;&gt; ~/.bashrc
source ~/.bashrc

# WSL-specific fixes:
npm config set os linux
export NODE_OPTIONS=--openssl-legacy-provider
```


## Step 4: Authentication and Configuration

**API Key Setup**:

1. Create account at [Anthropic Console](https://console.anthropic.com)
2. Generate API key with "Claude Code Full Access" scope
3. Set environment variable:
```bash
echo 'export ANTHROPIC_API_KEY="sk-your-key-here"' &gt;&gt; ~/.bashrc
source ~/.bashrc
```

**Initial Configuration**:

```bash
claude config set --global theme dark
claude config set --global verbose false
claude config set --global autoUpdaterStatus enabled
```


## Step 5: Project Setup and Basic Usage

**Initialize Project**:

```bash
mkdir my-agentic-project &amp;&amp; cd my-agentic-project
git init
claude init  # Creates CLAUDE.md project memory file
```

**Sample Workflow**:

```bash
claude "Implement user authentication module with JWT"
&gt; fix the TypeScript errors in auth.service.ts
&gt; run tests and fix any failures
&gt; create PR with title 'feat: Add JWT authentication'
```

**Key Commands**:

```bash
# Interactive REPL:
claude

# One-off command execution:
claude -p "Refactor user model to use TypeORM decorators"

# Pipeline integration: 
cat error.log | claude -p "Analyze stack trace and suggest fixes"
```


## Step 6: Advanced MCP Server Configuration

**Example Brave Search MCP Setup**:

```bash
git clone https://github.com/modelcontextprotocol/servers.git
cd servers/src/brave-search
npm install
BRAVE_API_KEY=your-key-here node index.js
```

**Register MCP Server**:

```bash
claude mcp add brave-search http://localhost:3000
claude config add --global allowedTools BraveSearch
```

**Sample MCP Query**:

```bash
claude "Find recent papers about Mixture-of-Experts architectures" --allowedTools BraveSearch
```


## Step 7: Automation and CI/CD Integration

**Headless Mode Example**:

```bash
claude -p "Run security audit and update dependencies" \
  --allowedTools "Bash(npm audit:*)" Edit \
  --output-format stream-json &gt; audit-results.json
```

**GitHub Actions Snippet**:

```yaml
name: Code Review
on: [pull_request]

jobs:
  claude-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm install -g @anthropic-ai/claude-code
      - run: |
          echo "ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }}" &gt;&gt; $GITHUB_ENV
          claude -p "Review PR changes for security issues" \
            --allowedTools "Bash(git diff:*)" Review
```


## Security Best Practices

1. **Permission Sandboxing**:
```bash
claude --dangerously-skip-permissions=false  # Default safe mode
```

2. **Network Restrictions**:
```bash
sudo ufw allow out 443/tcp  # Anthropic API
sudo ufw default deny outgoing
```

3. **Session Isolation**:
```bash
docker run -it --rm -v $(pwd):/code node:20-slim \
  sh -c "npm install -g @anthropic-ai/claude-code &amp;&amp; claude"
```


## Troubleshooting Guide

**Common Issues**:


| Symptom | Solution |
| :-- | :-- |
| `EACCES` permissions | Use `npm config set prefix ~/.npm-global`[^2] |
| WSL path errors | `npm config set script-shell /bin/bash`[^18] |
| API connection failures | Verify `ANTHROPIC_API_KEY` in WSL environment[^10] |
| MCP server timeouts | Check firewall rules and port forwarding[^15] |

**Diagnostic Commands**:

```bash
claude doctor --full  # Comprehensive system check
claude config list --show-secrets  # Verify environment
rg -i 'error|warn' ~/.claude/logs/  # Log analysis
```


## Performance Optimization

**Token Management**:

```bash
claude config set --global ANTHROPIC_SMALL_FAST_MODEL=claude-3-5-haiku-20241022
claude config set --global maxTokens 4096
```

**Caching Strategies**:

```bash
claude config set --global promptCache true
claude config set --global cacheTTL 3600
```

**Parallel Execution**:

```bash
claude batch "Process user_{1..100}.json" \
  -c "Normalize JSON schema and add metadata" \
  --workers 8
```

> "Claude Code's true power emerges when you treat it as a programmable agent rather than just a code generator. The ability to chain tool calls and maintain session context enables workflows that traditional AI coding tools can't match." - Anthropic Engineering Team[^6]

## Next Steps and Advanced Configuration

1. **Custom Tool Development**:
Implement MCP servers for internal APIs using the Model Context Protocol specification[^9][^15]
2. **Hybrid Workflows**:
Combine Claude Code with CI/CD pipelines for automated code reviews and deployment checks[^6]
3. **Enterprise Security**:
Set up Claude Code with private LLM deployments using Amazon Bedrock or Azure AI Studio[^16]
4. **Performance Monitoring**:
Integrate with Prometheus/Grafana for token usage tracking and cost optimization[^10]

This comprehensive setup establishes Claude Code as a full-stack engineering assistant capable of handling everything from routine refactoring to complex system design tasks. Regular updates and community contributions continue to expand its capabilities - stay current with `claude update` and monitor the official Anthropic documentation for new features[^2][^11].

<div style="text-align: center">⁂</div>

[^1]: https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/66167708/6143ef0a-8b4d-45cc-aebe-0950abbfb4ff/paste.txt

[^2]: https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview

[^3]: https://github.com/dvcrn/anthropic-cli

[^4]: https://apidog.com/blog/claude-code/

[^5]: https://www.youtube.com/watch?v=oM2dXJnD80c

[^6]: https://www.anthropic.com/engineering/claude-code-best-practices

[^7]: https://www.reddit.com/r/ChatGPTCoding/comments/1iyxtay/how_to_install_and_use_claude_code_maybe_the_best/

[^8]: https://www.youtube.com/watch?v=_yt4Trm-fRQ

[^9]: https://github.com/auchenberg/claude-code-mcp/blob/devin/1741367190-claude-code-mcp-setup/README.md

[^10]: https://www.restack.io/p/anthropic-answer-api-key-claude-models-cat-ai

[^11]: https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/tutorials

[^12]: https://www.codecademy.com/article/claude-code-tutorial-how-to-generate-debug-and-document-code-with-ai

[^13]: https://aider.chat/docs/llms/anthropic.html

[^14]: https://www.youtube.com/watch?v=NQNrPaDPMiA

[^15]: https://scottspence.com/posts/getting-mcp-server-working-with-claude-desktop-in-wsl

[^16]: https://www.acorn.io/resources/learning-center/claude-api/

[^17]: https://www.datacamp.com/tutorial/claude-code

[^18]: https://github.com/anthropics/claude-code/issues/188

[^19]: https://github.com/anthropics/claude-code

[^20]: https://www.reddit.com/r/ClaudeAI/comments/1enle9c/can_someone_explain_how_to_actually_use_claude/

[^21]: https://www.youtube.com/watch?v=z37_rONQof8

[^22]: https://docs.anthropic.com/en/docs/initial-setup

[^23]: https://www.youtube.com/watch?v=AJpK3YTTKZ4

[^24]: https://claude.ai

[^25]: https://www.reddit.com/r/Anthropic/comments/1dsr5j8/i_created_a_simple_cli_tool_to_easily_interface/

[^26]: https://www.reddit.com/r/ClaudeAI/comments/1dsudc4/how_to_use_claude_projects_for_coding/

[^27]: https://www.reddit.com/r/ChatGPTCoding/comments/1iyxtay/how_to_install_and_use_claude_code_maybe_the_best/

[^28]: https://github.com/anthropics/claude-code/issues/581

[^29]: https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/tutorials

[^30]: https://thinktank.ottomator.ai/t/archon-and-claude-code/6123

[^31]: https://www.marktechpost.com/2025/04/21/anthropic-releases-a-comprehensive-guide-to-building-coding-agents-with-claude-code/

[^32]: https://www.youtube.com/watch?v=NQNrPaDPMiA

[^33]: https://modelcontextprotocol.io/quickstart/server

[^34]: https://github.com/anthropics/claude-code/issues/507

[^35]: https://www.reddit.com/r/ClaudeAI/comments/1iztm9b/how_to_get_mcp_servers_running_on_claude_code/

[^36]: https://www.reddit.com/r/ClaudeAI/comments/1j7ck2z/using_claude_code_on_cicd/

[^37]: https://www.youtube.com/watch?v=3W8pjngjx3o

[^38]: https://publish.obsidian.md/aixplore/AI+Development+\&+Agents/claude-code-best-practices

[^39]: https://github.com/anthropics/claude-code/issues/630

[^40]: https://www.datacamp.com/tutorial/getting-started-with-claude-3-and-the-claude-3-api

[^41]: https://github.com/anthropics/courses/blob/master/anthropic_api_fundamentals/01_getting_started.ipynb

[^42]: https://docs.exa.ai/reference/tool-calling-with-claude

