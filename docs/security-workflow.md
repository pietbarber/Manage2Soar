# Security Scanning Workflow for Manage2Soar

This document outlines the security scanning setup and workflow for the Manage2Soar Django project.

## Overview

We use multiple layers of security scanning to protect the application:

1. **Bandit** - Static analysis for Python security issues
2. **Safety** - Vulnerability scanning for Python dependencies
3. **pip-audit** - Alternative dependency vulnerability scanner
4. **Pre-commit hooks** - Automated checks before commits
5. **CI/CD integration** - Automated scanning on pull requests and releases

## Security Architecture

```mermaid
graph TB
    subgraph "Developer Workstation"
        A[Developer Code] --> B[Pre-commit Hooks]
        B --> C{Security Check Pass?}
        C -->|Yes| D[Git Commit]
        C -->|No| E[Fix Issues]
        E --> A
    end

    subgraph "Security Tools"
        F[Bandit<br/>Static Analysis] --> B
        G[Safety<br/>Dependency Check] --> B
        H[Private Key Detection] --> B
        I[YAML/JSON Validation] --> B
    end

    subgraph "CI/CD Pipeline"
        D --> J[GitHub Push]
        J --> K[GitHub Actions]
        K --> L[Security Workflow]
        L --> M[Bandit Scan]
        L --> N[Safety Check]
        L --> O[pip-audit]
        M --> P{High Severity?}
        N --> P
        O --> P
        P -->|Yes| Q[Block Merge]
        P -->|No| R[Allow Merge]
        Q --> S[Security Alert]
        R --> T[Deploy to Production]
    end

    subgraph "Monitoring"
        U[Weekly Scheduled Scan] --> K
        V[Security Artifacts] --> W[Security Dashboard]
        M --> V
        N --> V
        O --> V
    end

    classDef security fill:#ff9999,stroke:#cc0000,stroke-width:2px
    classDef process fill:#99ccff,stroke:#0066cc,stroke-width:2px
    classDef success fill:#99ff99,stroke:#00cc00,stroke-width:2px
    classDef alert fill:#ffcc99,stroke:#ff6600,stroke-width:2px

    class F,G,H,I,M,N,O security
    class B,K,L process
    class R,T success
    class Q,S alert
```

## Security Tools Configuration

### Tool Integration Architecture

```mermaid
graph LR
    subgraph "Configuration Files"
        A[bandit.yaml] --> B[Bandit Scanner]
        C[.pre-commit-config.yaml] --> D[Pre-commit Framework]
        E[.github/workflows/security.yml] --> F[GitHub Actions]
    end

    subgraph "Security Tools"
        B --> G[Static Code Analysis]
        H[Safety] --> I[Dependency Vulnerability Check]
        J[pip-audit] --> K[Alternative Dependency Check]
        L[detect-private-key] --> M[Secret Detection]
        N[check-yaml] --> O[Configuration Validation]
    end

    subgraph "Integration Points"
        D --> B
        D --> H
        D --> L
        D --> N
        F --> B
        F --> H  
        F --> J
    end

    subgraph "Reporting"
        G --> P[Security Issues Report]
        I --> P
        K --> P
        M --> P
        O --> P
        P --> Q[Developer Feedback]
        P --> R[CI/CD Decision]
    end

    classDef config fill:#e3f2fd,stroke:#1976d2
    classDef tool fill:#f1f8e9,stroke:#388e3c
    classDef integration fill:#fff8e1,stroke:#f57c00
    classDef output fill:#fce4ec,stroke:#c2185b

    class A,C,E config
    class B,H,J,L,N tool
    class D,F integration
    class P,Q,R output
```

### Bandit Configuration (`bandit.yaml`)

Our Bandit configuration focuses on real security issues while excluding test noise:

```yaml
# Excluded directories and file patterns
exclude_dirs: ['.venv', 'staticfiles', 'generated_avatars', 'media', 'tinymce']
exclude: ['*/test_*.py', '*/tests/*', '*/migrations/*', 'conftest.py']

# Security tests to skip (false positives)
skips: ['B101', 'B106', 'B308', 'B601', 'B703']

# Focus on medium+ severity issues  
severity: 'medium'
confidence: 'medium'
```

### Pre-commit Hook Security Stack

```mermaid
flowchart TD
    A[Developer Commit] --> B[Pre-commit Triggered]

    subgraph "Security Hooks"
        B --> C[Bandit Security Scan]
        B --> D[Private Key Detection]
        B --> E[AWS Credentials Check]
        B --> F[Large File Detection]
    end

    subgraph "Quality Hooks"  
        B --> G[YAML/JSON Validation]
        B --> H[Django Security Upgrades]
        B --> I[Python Safety Check]
        B --> J[Code Formatting]
    end

    subgraph "Results Processing"
        C --> K{Security Issues?}
        D --> K
        E --> K
        F --> K
        G --> L{Format Issues?}
        H --> L
        I --> M{Vulnerabilities?}
        J --> L
    end

    K -->|Issues Found| N[Block Commit]
    K -->|Clean| O[Continue]
    L -->|Issues Found| P[Auto-fix + Retry]
    L -->|Clean| O
    M -->|Critical Vulns| N
    M -->|Safe| O

    N --> Q[Show Error Report]
    O --> R[Allow Commit]
    P --> S[Review Auto-fixes]

    classDef security fill:#ffcdd2,stroke:#d32f2f
    classDef quality fill:#c8e6c9,stroke:#388e3c
    classDef decision fill:#fff3e0,stroke:#f57c00
    classDef result fill:#e1f5fe,stroke:#0288d1

    class C,D,E,F security
    class G,H,I,J quality
    class K,L,M decision
    class R,Q,S result
```

## Development Workflow

### Daily Development Process

```mermaid
flowchart TD
    A[Developer Starts Work] --> B[Write/Modify Code]
    B --> C[git add .]
    C --> D[git commit -m "message"]
    D --> E[Pre-commit Hooks Execute]

    E --> F{Bandit Check}
    F -->|Pass| G{Safety Check}
    F -->|Fail| H[Fix Security Issues]

    G -->|Pass| I{Format Checks}
    G -->|Fail| J[Update Dependencies]

    I -->|Pass| K[Commit Success]
    I -->|Fail| L[Auto-fix Formatting]

    H --> M[Add Security Fix]
    J --> N[Review Vulnerabilities]
    L --> O[Review Changes]

    M --> B
    N --> P{Critical Vuln?}
    O --> Q{Acceptable?}

    P -->|Yes| R[Emergency Fix]
    P -->|No| S[Plan Upgrade]
    Q -->|Yes| C
    Q -->|No| B

    R --> B
    S --> T[Create Issue]
    T --> U[Continue Development]
    U --> C

    K --> V[Push to GitHub]
    V --> W[CI/CD Pipeline Triggered]

    classDef success fill:#d4edda,stroke:#155724
    classDef warning fill:#fff3cd,stroke:#856404
    classDef error fill:#f8d7da,stroke:#721c24
    classDef process fill:#cce5ff,stroke:#004085

    class K,V success
    class J,L,O warning
    class H,R error
    class E,F,G,I process
```

### Setup Instructions

1. **Install pre-commit hooks** (one-time setup):
   ```bash
   pip install pre-commit
   pre-commit install
   ```

2. **Normal commits automatically trigger security checks**:
   ```bash
   git add .
   git commit -m "Your commit message"
   # Pre-commit hooks run automatically
   ```

3. **Manual security scan** (optional):
   ```bash
   bandit -r . --configfile bandit.yaml
   ```

### Handling Security Issues

#### When Pre-commit Hooks Fail

1. **Review the security issue** reported by the hook
2. **Fix the issue** in your code
3. **Re-commit** - hooks will run again
4. If it's a **false positive**, add `# nosec` comment with justification:
   ```python
   password = "test123"  # nosec B105 - This is a test fixture password
   ```

#### Security Issue Priority

- **HIGH severity**: Must be fixed before merging
- **MEDIUM severity**: Should be reviewed and addressed
- **LOW severity**: Can be addressed in follow-up work

### Pull Request Security Process

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant GH as GitHub
    participant CI as CI/CD Pipeline
    participant Rev as Reviewer
    participant Sec as Security Scanner

    Dev->>GH: Create Pull Request
    GH->>CI: Trigger Security Workflow
    CI->>Sec: Run Bandit Scan
    CI->>Sec: Run Safety Check
    CI->>Sec: Run pip-audit

    Sec-->>CI: Security Results

    alt High Severity Issues Found
        CI->>GH: Block Merge + Comment
        GH->>Dev: Security Alert
        Dev->>Dev: Fix Security Issues
        Dev->>GH: Push Updated Code
        GH->>CI: Re-trigger Security Scan
    else No High Severity Issues
        CI->>GH: Allow Merge + Report
        GH->>Rev: Ready for Review
        Rev->>Rev: Review Code + Security

        alt Reviewer Approves
            Rev->>GH: Approve PR
            GH->>GH: Merge to Main
        else Reviewer Requests Changes
            Rev->>Dev: Request Changes
            Dev->>GH: Update PR
        end
    end

    Note over CI,Sec: Weekly scheduled scans<br/>also run independently
```

### PR Security Checklist

1. **Create pull request** - triggers automated security scanning
2. **Review security scan results** in the PR comments
3. **Address any HIGH severity issues** before approval
4. **Security gate** will block merge if high-severity issues exist
5. **Document security fixes** in PR description if applicable

## CI/CD Integration

### GitHub Actions Security Pipeline

```mermaid
graph TB
    subgraph "Trigger Events"
        A[Push to main/develop] --> E[Security Workflow]
        B[Pull Request] --> E
        C[Weekly Schedule<br/>Sunday 2 AM UTC] --> E
        D[Manual Trigger] --> E
    end

    subgraph "Security Workflow Steps"
        E --> F[Checkout Code]
        F --> G[Setup Python Environment]
        G --> H[Install Dependencies]
        H --> I[Run Bandit Scan]
        H --> J[Run Safety Check]
        H --> K[Run pip-audit]

        I --> L{High Severity<br/>Issues Found?}
        J --> L
        K --> L

        L -->|Yes| M[Fail Build]
        L -->|No| N[Pass Build]

        M --> O[Generate Security Report]
        N --> O
        O --> P[Upload Artifacts]
        P --> Q[Comment on PR]
        Q --> R[Send Notifications]
    end

    subgraph "Artifact Storage"
        S[Bandit Results JSON]
        T[Safety Report]
        U[pip-audit Output]
        V[Security Summary]
        P --> S
        P --> T
        P --> U
        P --> V
    end

    subgraph "Notification Channels"
        R --> W[GitHub PR Comments]
        R --> X[GitHub Issue Creation]
        R --> Y[Team Slack Channel]
        R --> Z[Email Alerts]
    end

    classDef trigger fill:#e1f5fe,stroke:#0277bd
    classDef security fill:#ffebee,stroke:#c62828
    classDef success fill:#e8f5e8,stroke:#2e7d32
    classDef fail fill:#ffebee,stroke:#c62828
    classDef storage fill:#f3e5f5,stroke:#7b1fa2
    classDef notify fill:#fff3e0,stroke:#ef6c00

    class A,B,C,D trigger
    class I,J,K,L security
    class N,P success
    class M,O fail
    class S,T,U,V storage
    class W,X,Y,Z notify
```

### Security Workflow Configuration
Located in `.github/workflows/security.yml`, this workflow:

- **Triggers on**: Pushes to main/develop, pull requests, weekly schedule
- **Runs**: Bandit, Safety, pip-audit scans  
- **Reports**: Upload scan results as artifacts
- **Comments**: Adds security summary to pull requests
- **Blocks**: Fails build on high-severity issues

### Scheduled Security Monitoring

```mermaid
gantt
    title Security Scanning Schedule
    dateFormat  X
    axisFormat %w

    section Daily
    Pre-commit Hooks        :active, daily, 0, 7

    section Weekly  
    Dependency Scan         :crit, weekly, 0, 1
    Vulnerability Database Update :weekly, 1, 2

    section Monthly
    Security Tool Updates   :monthly, 4, 5
    Security Config Review  :monthly, 5, 6

    section Quarterly
    Security Audit         :quarterly, 6, 7
    Tool Evaluation        :quarterly, 6, 7
```

## Security Issue Response

### Security Incident Response Workflow

```mermaid
flowchart TD
    A[Security Issue Detected] --> B{Severity Level}

    B -->|CRITICAL/HIGH| C[IMMEDIATE ACTION]
    B -->|MEDIUM| D[STANDARD PROCESS]
    B -->|LOW| E[BACKLOG PROCESS]

    subgraph "Critical/High Severity Response"
        C --> F[Stop Deployment Pipeline]
        F --> G[Create Hotfix Branch]
        G --> H[Security Team Notification]
        H --> I[Develop Emergency Fix]
        I --> J[Emergency Testing]
        J --> K{Fix Verified?}
        K -->|No| I
        K -->|Yes| L[Deploy Hotfix]
        L --> M[Monitor Production]
        M --> N[Post-Incident Review]
        N --> O[Update Security Docs]
    end

    subgraph "Medium Severity Process"
        D --> P[Create GitHub Issue]
        P --> Q[Assign Security Label]
        Q --> R[Developer Assignment]
        R --> S[Plan in Next Sprint]
        S --> T[Implement Fix]
        T --> U[Code Review]
        U --> V[Security Testing]
        V --> W[Deploy with Release]
    end

    subgraph "Low Severity Process"
        E --> X[Add to Security Backlog]
        X --> Y[Quarterly Review]
        Y --> Z[Batch Fix Planning]
        Z --> AA[Include in Maintenance]
    end

    classDef critical fill:#ff4444,stroke:#cc0000,color:#fff
    classDef medium fill:#ffaa44,stroke:#cc6600,color:#000
    classDef low fill:#44ff44,stroke:#00cc00,color:#000
    classDef process fill:#4444ff,stroke:#0000cc,color:#fff

    class C,F,G,H,I,J,K,L,M,N,O critical
    class D,P,Q,R,S,T,U,V,W medium  
    class E,X,Y,Z,AA low
    class A,B process
```

### Response Time Requirements

| Severity | Response Time | Resolution Time | Escalation |
|----------|---------------|-----------------|------------|
| **CRITICAL** | < 1 hour | < 24 hours | Immediate to Security Team |
| **HIGH** | < 4 hours | < 72 hours | Team Lead notification |
| **MEDIUM** | < 1 day | < 2 weeks | Standard assignment |
| **LOW** | < 1 week | Next quarter | Backlog review |

## Common Security Patterns

### Safe Coding Practices

✅ **DO**:
```python
import requests
from django.utils.html import escape

# Use timeouts on external requests
response = requests.get(url, timeout=10)

# Escape user input before mark_safe
safe_content = mark_safe(f"<p>{escape(user_input)}</p>")
```

❌ **DON'T**:
```python
# No timeout - can hang indefinitely
response = requests.get(url)

# Raw user input in mark_safe - XSS risk
unsafe_content = mark_safe(f"<p>{user_input}</p>")
```

### Django Security Settings

- **DEBUG = False** in production
- **SECURE_SSL_REDIRECT = True** for HTTPS
- **CSRF protection** enabled
- **XSS protection** headers set
- **Content Security Policy** configured

## Troubleshooting

### Common Issues

1. **Pre-commit hooks slow/failing**:
   ```bash
   pre-commit run --all-files  # Run on all files
   pre-commit clean  # Clear cache
   ```

2. **False positive security warnings**:
   - Add `# nosec B###` comment with justification
   - Update `.bandit` configuration if pattern is common

3. **CI security scans failing**:
   - Check GitHub Actions logs for specific errors
   - Verify all dependencies are properly installed
   - Review security scan artifacts for details

### Getting Help

- **Security questions**: Ask in team Slack #security channel
- **Tool issues**: Check tool documentation or create GitHub issue
- **Urgent security concerns**: Contact security team immediately

## Updating Security Tools

### Regular Maintenance

- **Monthly**: Update pre-commit hook versions
- **Quarterly**: Review and update security tool configurations
- **As needed**: Add new security tools or rules

### Version Updates

1. **Update `.pre-commit-config.yaml`** with new versions
2. **Test locally** with `pre-commit run --all-files`
3. **Update CI workflow** if needed
4. **Document changes** in team communication

## Security Defense Layers

```mermaid
graph TB
    subgraph "Security Defense in Depth"
        subgraph "Layer 1: Developer Environment"
            A[IDE Security Extensions] --> B[Pre-commit Hooks]
            B --> C[Local Security Scans]
        end

        subgraph "Layer 2: Repository Controls"  
            D[Branch Protection Rules] --> E[Required Status Checks]
            E --> F[Security Scan Gates]
        end

        subgraph "Layer 3: CI/CD Pipeline"
            G[Automated Security Testing] --> H[Dependency Scanning]
            H --> I[Static Code Analysis]
            I --> J[Security Artifact Generation]
        end

        subgraph "Layer 4: Deployment Security"
            K[Infrastructure Security] --> L[Runtime Protection]
            L --> M[Monitoring & Alerting]
        end

        subgraph "Layer 5: Production Monitoring"
            N[Security Logging] --> O[Incident Response]
            O --> P[Threat Detection]
        end
    end

    C --> D
    F --> G  
    J --> K
    M --> N
    P --> Q[Security Feedback Loop]
    Q --> A

    classDef layer1 fill:#e8f5e8,stroke:#2e7d32
    classDef layer2 fill:#e3f2fd,stroke:#1976d2  
    classDef layer3 fill:#fff3e0,stroke:#f57c00
    classDef layer4 fill:#fce4ec,stroke:#c2185b
    classDef layer5 fill:#f3e5f5,stroke:#7b1fa2
    classDef feedback fill:#ffebee,stroke:#d32f2f

    class A,B,C layer1
    class D,E,F layer2
    class G,H,I,J layer3
    class K,L,M layer4
    class N,O,P layer5
    class Q feedback
```

### Security Tool Effectiveness Matrix

| Tool | Code Issues | Dependencies | Secrets | Config | Runtime |
|------|-------------|--------------|---------|--------|---------|
| **Bandit** | ✅ High | ❌ None | ⚠️ Limited | ❌ None | ❌ None |
| **Safety** | ❌ None | ✅ High | ❌ None | ❌ None | ❌ None |
| **pip-audit** | ❌ None | ✅ High | ❌ None | ❌ None | ❌ None |
| **detect-private-key** | ❌ None | ❌ None | ✅ High | ❌ None | ❌ None |
| **Pre-commit** | ✅ Medium | ✅ Medium | ✅ High | ✅ Medium | ❌ None |
| **GitHub Actions** | ✅ High | ✅ High | ✅ Medium | ✅ Medium | ❌ None |

---

## Quick Reference Commands

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `bandit -r . --configfile bandit.yaml` | Manual security scan | Before major commits |
| `bandit -r . --configfile bandit.yaml --severity-level high` | High severity only | Critical issue check |
| `pre-commit run --all-files` | Run all pre-commit hooks | After config changes |
| `pre-commit run bandit --all-files` | Run only Bandit hook | Security-focused check |
| `safety check` | Check dependencies for vulnerabilities | Dependency updates |
| `pip-audit` | Alternative dependency vulnerability check | Cross-validation |
| `pre-commit autoupdate` | Update hook versions | Monthly maintenance |
| `pre-commit clean` | Clear hook cache | Troubleshooting |

### Emergency Security Commands

```bash
# Stop all running processes
git stash  # Save current work
git checkout main  # Switch to stable branch

# Emergency security scan
bandit -r . --configfile bandit.yaml --severity-level high --format json -o security-emergency.json

# Create hotfix branch
git checkout -b hotfix/security-$(date +%Y%m%d)

# After fix, test security
pre-commit run --all-files
pytest --no-cov  # Quick test run
```

### Configuration Files Reference

- **`bandit.yaml`** - Bandit security scanner configuration
- **`.pre-commit-config.yaml`** - Pre-commit hooks configuration  
- **`.github/workflows/security.yml`** - CI/CD security pipeline
- **`.vscode/settings.json`** - VS Code security extensions config

For questions or security concerns, contact the development team or create a GitHub issue with the `security` label.
