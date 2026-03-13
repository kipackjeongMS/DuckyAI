# DuckyAI — System Design Document

> **Generated:** 2026-03-11  
> **Version:** 0.0.18  
> **Type:** Architecture / System Design

---

## 1. Overview

**DuckyAI** is an AI-powered personal knowledge management (PKM) platform that combines an **Obsidian vault**, a **Python orchestrator daemon**, a **TypeScript MCP server**, and **GitHub Copilot / Claude Code integration** into a unified automation system.

The core idea: give AI assistants **persistent memory** of your work by storing everything in markdown files, then automate repetitive knowledge management tasks through event-driven agents.

### Key Capabilities

| Capability | How |
|---|---|
| **Automated document ingestion** | File watcher detects new files → AI enriches and organizes them |
| **Scheduled summaries** | Cron-triggered agents generate daily roundups, topic indexes |
| **Teams integration** | Hourly sync of chats & meetings into vault notes |
| **Interactive PKM** | Copilot prompts for creating tasks, meetings, investigations |
| **Multi-executor AI** | Supports Claude Code, Copilot SDK, Gemini CLI as agent backends |

---

## 2. High-Level Architecture

```mermaid
graph TB
    subgraph UI["User Interfaces"]
        direction LR
        OBS[Obsidian]
        VSC[VS Code + Copilot]
        DSK[Desktop App - Tauri]
        CLI_CMD[duckyai CLI]
    end

    subgraph AI["AI Layer"]
        direction LR
        CC[Claude Code]
        CS[Copilot SDK]
        GC[Gemini CLI]
    end

    subgraph CORE["DuckyAI Core"]
        direction TB
        MCP[MCP Server - TypeScript]
        ORCH[Orchestrator Daemon - Python]
        CFG[duckyai.yml Config]
    end

    subgraph VAULT["Obsidian Vault - Markdown Files"]
        direction LR
        INB[00-Inbox]
        WRK[01-Work]
        PPL[02-People]
        KNW[03-Knowledge]
        PER[04-Periodic]
        ARC[05-Archive]
    end

    subgraph EXT["External Sources"]
        direction LR
        TEAMS[Microsoft Teams]
        ADO[Azure DevOps]
        ANOTES[Apple Notes]
    end

    UI --> AI
    AI <--> MCP
    MCP <--> VAULT
    ORCH --> AI
    ORCH --> VAULT
    CFG --> ORCH
    EXT --> ORCH
    CLI_CMD --> ORCH
```

---

## 3. Component Architecture

### 3.1 Orchestrator Daemon (Python)

The heart of automation. A long-running daemon that reacts to file system events and cron schedules to trigger AI agents.

```mermaid
graph TB
    subgraph DAEMON["Orchestrator Daemon"]
        direction TB
        CORE[core.py - Event Loop]

        subgraph INPUTS["Event Sources"]
            direction LR
            FM[FileMonitor - watchdog]
            CS_[CronScheduler - croniter]
            PM[PollerManager]
        end

        subgraph PROCESSING["Processing"]
            direction LR
            AR[AgentRegistry]
            EM[ExecutionManager]
            TM[TaskManager]
        end

        INPUTS --> CORE
        CORE --> AR
        AR --> EM
        EM --> TM
    end

    FM -->|TriggerEvent| CORE
    CS_ -->|TriggerEvent| CORE
    PM -->|TriggerEvent| CORE

    EM -->|subprocess| EXEC[AI Executor]
    TM -->|write| TASKS[Task Files]
    EM -->|write| LOGS[Log Files]
```

#### Component Responsibilities

| Component | File | Purpose |
|---|---|---|
| **Core** | `core.py` | Main event loop; coordinates all subsystems |
| **FileMonitor** | `file_monitor.py` | Watches vault via `watchdog`; debounces events (500ms) |
| **CronScheduler** | `cron_scheduler.py` | Evaluates cron expressions every 60s; 10-min cooldown |
| **PollerManager** | `poller_manager.py` | Polls external sources (Apple Notes, Teams) |
| **AgentRegistry** | `agent_registry.py` | Loads agent definitions from `duckyai.yml` nodes |
| **ExecutionManager** | `execution_manager.py` | Manages concurrency limits; invokes AI executors |
| **TaskManager** | `task_manager.py` | Creates/updates task tracking files for audit |

#### Orchestrator Event Flow

```mermaid
sequenceDiagram
    participant FS as File System
    participant FM as FileMonitor
    participant Q as Event Queue
    participant EL as Event Loop
    participant AR as AgentRegistry
    participant EM as ExecutionManager
    participant AI as AI Executor
    participant V as Vault

    FS->>FM: File created/modified
    FM->>FM: Debounce (500ms)
    FM->>Q: Queue TriggerEvent
    EL->>Q: Poll (1s interval)
    Q->>EL: TriggerEvent
    EL->>AR: find_agents_for(event)
    AR->>EL: Matching agents
    EL->>EM: queue_execution(agent, event)
    EM->>EM: Check concurrency limits
    EM->>AI: Spawn subprocess
    AI->>V: Read/Write vault files
    AI->>EM: Exit code + output
    EM->>EM: Update task status
```

### 3.2 MCP Server (TypeScript)

Exposes vault operations as standardized tools to AI assistants via the Model Context Protocol.

```mermaid
graph LR
    subgraph CLIENTS["AI Clients"]
        COP[GitHub Copilot]
        CLA[Claude Desktop]
    end

    subgraph MCP_SRV["MCP Server - stdio transport"]
        direction TB
        IDX[index.ts]

        subgraph TOOLS["19 MCP Tools"]
            direction LR
            T1[prepareDailyNote]
            T2[createTask]
            T3[logAction]
            T4[generateRoundup]
            T5[triageInbox]
            T6[enrichNote]
            T7[updateTopicIndex]
            T8[createMeeting]
            T9[create1on1]
            T10[archiveTask]
            T11[updateTaskStatus]
            T12[logPRReview]
            T13[prepareWeeklyReview]
            T14[getTeamsChatSyncState]
            T15[updateTeamsChatSyncState]
            T16[appendTeamsChatHighlights]
            T17[getTeamsMeetingSyncState]
            T18[updateTeamsMeetingSyncState]
            T19[appendTeamsMeetingHighlights]
        end
    end

    CLIENTS <-->|stdio| IDX
    IDX --> TOOLS
    TOOLS -->|read/write| VAULT_FILES[Vault Markdown Files]
    TOOLS -->|read/write| STATE[Global State Files]
```

#### Key MCP Tool Categories

| Category | Tools | Description |
|---|---|---|
| **Daily Notes** | `prepareDailyNote`, `logAction`, `logPRReview` | Create and append to daily notes |
| **Task Management** | `createTask`, `updateTaskStatus`, `archiveTask` | Full task lifecycle |
| **Meetings** | `createMeeting`, `create1on1` | Meeting note creation |
| **Aggregation** | `generateRoundup`, `prepareWeeklyReview`, `updateTopicIndex` | Summarize and index |
| **Organization** | `triageInbox`, `enrichNote` | Process and structure content |
| **Teams Sync** | `get/updateTeamsChatSyncState`, `appendTeamsChat/MeetingHighlights` | Watermark-based Teams integration |

### 3.3 CLI (`duckyai`)

Python Click-based CLI providing orchestrator control and vault operations.

```
duckyai
├── init                              # Initialize vault
├── setup                             # First-time OOBE
├── show-config                       # Display duckyai.yml
├── template list|new                 # Template operations
├── trigger [AGENT_ABBR]              # Manually trigger agent
├── update                            # Update vault from template
├── voice                             # Voice input mode
├── orchestrator
│   ├── start                         # Start daemon (PID file)
│   ├── stop                          # Stop daemon
│   ├── status                        # Check status
│   ├── list-agents                   # Show loaded agents
│   └── trigger [ABBR]               # Trigger single agent
└── -o / --orchestrator               # Run daemon mode
```

### 3.4 Vault Structure

The Obsidian vault is the central data store — all content is markdown with YAML frontmatter.

```mermaid
graph TB
    subgraph VAULT["DuckyAI Vault"]
        direction TB

        subgraph CAPTURE["Capture"]
            INB["00-Inbox/ - Quick capture, unsorted"]
        end

        subgraph WORK["Work"]
            TASKS["01-Work/Tasks/ - P0-P3 prioritized"]
            PROJ["01-Work/Projects/ - Multi-task initiatives"]
            INV["01-Work/Investigations/ - Technical deep-dives"]
        end

        subgraph PEOPLE["People"]
            ONES["02-People/1-on-1s/"]
            MEET["02-People/Meetings/"]
            CONT["02-People/Contacts/"]
        end

        subgraph KNOWLEDGE["Knowledge"]
            DOCS["03-Knowledge/Documentation/"]
            TOPICS["03-Knowledge/Topics/"]
        end

        subgraph PERIODIC["Periodic"]
            DAILY["04-Periodic/Daily/ - YYYY-MM-DD.md"]
            WEEKLY["04-Periodic/Weekly/ - YYYY-Www.md"]
        end

        ARC["05-Archive/ - Completed items"]
    end

    INB -->|EIC Agent| DOCS
    INB -->|EDM Agent| DOCS
    TASKS -->|archiveTask| ARC
    DAILY -->|GDR Agent| DAILY
    DOCS -->|TIU Agent| TOPICS
```

---

## 4. Agent System

### 4.1 Configured Agents (6)

```mermaid
graph LR
    subgraph FILE_TRIGGERED["File-Triggered Agents"]
        EIC["EIC - Enrich Ingested Content"]
        EDM["EDM - Extract Document to Markdown"]
    end

    subgraph CRON_TRIGGERED["Cron-Triggered Agents"]
        GDR["GDR - Generate Daily Roundup<br/>6 PM Mon-Fri"]
        TIU["TIU - Topic Index Update<br/>6:30 PM Fridays"]
        TCS["TCS - Teams Chat Summary<br/>Hourly at :10"]
        TMS["TMS - Teams Meeting Summary<br/>Hourly at :10"]
    end

    INB[00-Inbox] -->|new file| EIC
    INB -->|pdf/docx/doc/txt| EDM
    EIC --> KNW[03-Knowledge]
    EDM --> KNW

    GDR --> DAILY[04-Periodic/Daily]
    TIU --> TOPICS[03-Knowledge/Topics]
    TCS --> DAILY
    TMS --> DAILY
```

| Agent | Abbr | Trigger | Input | Output | Executor |
|---|---|---|---|---|---|
| Enrich Ingested Content | EIC | File created in `00-Inbox/` | `00-Inbox/*.md` | `03-Knowledge/Documentation/` | claude_code |
| Extract Document to Markdown | EDM | File created in `00-Inbox/` | `00-Inbox/*.pdf\|*.docx` | New `.md` file | claude_code |
| Generate Daily Roundup | GDR | Cron: `0 18 * * 1-5` | Scans vault | `04-Periodic/Daily/` | claude_code |
| Topic Index Update | TIU | Cron: `30 18 * * 5` | `04-Periodic/Daily/` | `03-Knowledge/Topics/` | claude_code |
| Teams Chat Summary | TCS | Cron: `10 * * * *` | Microsoft Graph API | Daily note update | copilot_sdk |
| Teams Meeting Summary | TMS | Cron: `10 * * * *` | Microsoft Graph API | Daily note + meeting files | copilot_sdk |

### 4.2 Agent Execution Model

```mermaid
graph TB
    TRIGGER[Trigger Event] --> MATCH{Agent Match?}
    MATCH -->|Yes| CAPACITY{Capacity Available?}
    MATCH -->|No| DISCARD[Discard Event]
    CAPACITY -->|No| QUEUE[Queue for Later]
    CAPACITY -->|Yes| BUILD[Build Execution Context]
    BUILD --> EXEC[Spawn AI Subprocess]

    EXEC --> LOAD[Load Agent Prompt]
    LOAD --> INJECT[Inject Skills + MCP Config]
    INJECT --> RUN[Execute with AI Model]
    RUN --> OUTPUT[Write Output to Vault]
    OUTPUT --> TRACK[Update Task File]
    TRACK --> DONE[Release Execution Slot]

    QUEUE -->|Slot freed| CAPACITY
```

**Concurrency Controls:**
- **Global limit:** `max_concurrent: 3` (across all agents)
- **Per-agent limit:** `max_parallel` per node definition
- **Cooldown:** 10 minutes between repeated cron triggers

---

## 5. Skills & Prompts System

### 5.1 GitHub Copilot Skills (21)

Skills are reusable knowledge modules defined as `SKILL.md` files in `.github/skills/`. Each skill has YAML frontmatter defining triggers and a markdown body containing instructions.

```mermaid
graph TB
    subgraph SKILLS["21 Copilot Skills"]
        direction TB

        subgraph PKM["Knowledge Management"]
            S1[daily-roundup]
            S2[triage-inbox]
            S3[docx-to-markdown]
        end

        subgraph OBS["Obsidian Standards"]
            S4[obsidian-canvas]
            S5[obsidian-cli]
            S6[obsidian-links]
            S7[obsidian-markdown-structure]
            S8[obsidian-mermaid]
            S9[obsidian-yaml-frontmatter]
        end

        subgraph SYS["System Management"]
            S10[orchestrator]
            S11[duckyai-cli]
            S12[system-status]
            S13[list-agents]
            S14[trigger-agent]
        end

        subgraph LIFECYCLE["Vault Lifecycle"]
            S15[vault-setup]
            S16[vault-update]
            S17[vault-publish]
        end

        subgraph TEAMS["Teams Integration"]
            S18[teams-chat-summary]
            S19[teams-meeting-summary]
        end

        subgraph META["Meta Skills"]
            S20[make-skill-template]
            S21[code-sanitization]
        end
    end
```

### 5.2 Copilot Prompts (7)

Interactive prompts triggered via `@workspace /command` in VS Code:

| Prompt | Command | Purpose |
|---|---|---|
| `new-task.prompt.md` | `/new-task` | Create prioritized task (P0–P3) |
| `new-meeting.prompt.md` | `/new-meeting` | Create meeting or 1:1 note |
| `new-investigation.prompt.md` | `/new-investigation` | Start technical deep-dive |
| `add-documentation.prompt.md` | `/add-documentation` | Add to knowledge base |
| `prioritize-work.prompt.md` | `/prioritize-work` | Get prioritized work view |
| `archive-task.prompt.md` | `/archive-task` | Complete and archive task |
| `restructure-document.prompt.md` | `/restructure-document` | Reformat content for vault |

---

## 6. Data Flow Diagrams

### 6.1 Document Ingestion Pipeline

```mermaid
sequenceDiagram
    participant U as User
    participant INB as 00-Inbox/
    participant FM as FileMonitor
    participant EDM as EDM Agent
    participant EIC as EIC Agent
    participant KNW as 03-Knowledge/
    participant TIU as TIU Agent
    participant TOP as Topics/

    U->>INB: Drop file (PDF/DOCX/MD)
    FM->>FM: Detect new file
    FM->>EDM: Trigger (if non-MD)
    EDM->>INB: Convert to Markdown
    FM->>EIC: Trigger (MD file)
    EIC->>EIC: Enrich with frontmatter, links, structure
    EIC->>KNW: Write enriched file
    Note over TIU: Friday 6:30 PM
    TIU->>KNW: Scan documentation
    TIU->>TOP: Create/update topic indexes
```

### 6.2 Daily Workflow Cycle

```mermaid
sequenceDiagram
    participant U as User
    participant MCP as MCP Server
    participant DN as Daily Note
    participant TCS as TCS Agent
    participant TMS as TMS Agent
    participant GDR as GDR Agent
    participant TEAMS as Microsoft Teams

    Note over U: Morning
    U->>MCP: prepareDailyNote
    MCP->>DN: Create with carry-forward items

    Note over U: Throughout Day
    U->>MCP: logAction / logPRReview / createTask
    MCP->>DN: Append to daily note

    Note over TCS,TMS: Every Hour at :10
    TCS->>TEAMS: Fetch new chats (watermark)
    TCS->>DN: Append Chat Highlights
    TMS->>TEAMS: Fetch new meetings (watermark)
    TMS->>DN: Append Meeting Highlights

    Note over GDR: 6:00 PM Weekdays
    GDR->>DN: Generate roundup summary
    GDR->>DN: Compute stats (tasks, meetings)
```

### 6.3 Task Lifecycle

```mermaid
stateDiagram-v2
    [*] --> todo: createTask
    todo --> in_progress: updateTaskStatus
    in_progress --> blocked: updateTaskStatus
    blocked --> in_progress: updateTaskStatus
    in_progress --> done: updateTaskStatus
    todo --> cancelled: updateTaskStatus
    in_progress --> cancelled: updateTaskStatus
    done --> archived: archiveTask
    cancelled --> archived: archiveTask
    archived --> [*]

    state "01-Work/Tasks/" as todo
    state "01-Work/Tasks/" as in_progress
    state "01-Work/Tasks/" as blocked
    state "05-Archive/" as archived
```

---

## 7. Configuration System

### 7.1 `duckyai.yml` Structure

```yaml
version: "0.0.18"
id: duckyai_vault
user:
  name: "User Name"
  primaryLanguage: ko
  timezone: "PST"

orchestrator:
  auto_start: true
  prompts_dir: .github/prompts-agent    # Agent system prompts
  skills_dir: .github/skills            # Reusable AI skills
  bases_dir: .github/bases              # Base configuration
  max_concurrent: 3                     # Global execution limit
  poll_interval: 1                      # Event queue poll (seconds)
  file_extensions: [.md, .pdf, .docx, .doc, .txt]

defaults:
  executor: claude_code                 # AI backend
  timeout_minutes: 30
  max_parallel: 3
  task_create: true
  task_priority: medium
  agent_params:
    model: claude-opus-4.6

nodes:                                  # Agent definitions
  - name: "Agent Name (ABBR)"
    type: agent
    input_path: "00-Inbox"              # File trigger path
    output_path: "03-Knowledge/"        # Where output goes
    cron: "0 18 * * 1-5"               # Or cron schedule
    enabled: true
    executor: claude_code               # Override default
    workers: [...]                      # Multi-executor comparison

pollers:                                # External data sources
  apple_notes:
    enabled: false
    target_dir: 00-Inbox
    poll_interval: 3600
```

### 7.2 Configuration Hierarchy

```mermaid
graph TB
    DY[duckyai.yml] --> SEC[secrets.yaml - merged]
    DY --> DEFAULTS[defaults section]
    DY --> NODES[nodes section]
    DY --> POLLERS[pollers section]

    DEFAULTS --> NODE_EXEC[Per-node override]
    DEFAULTS --> GLOBAL[Global settings]

    NODES --> AGENT[AgentDefinition objects]
    AGENT --> EXEC_CTX[ExecutionContext]

    SEC -->|API keys, tokens| EXEC_CTX

    ENV[CLI --config-file flag] -->|Override| DY
```

---

## 8. Runtime Architecture

### 8.1 File System Layout

```
~/.duckyai/                            # Global DuckyAI home
└── vaults/{vault_id}/                 # Per-vault runtime data
    ├── state/                         # Sync watermarks
    │   ├── tcs-last-sync.json         # Teams Chat sync state
    │   └── tms-last-sync.json         # Teams Meeting sync state
    ├── tasks/                         # Agent execution tracking
    │   └── YYYY-MM-DD ABBR - desc.md  # Task files (QUEUED/RUNNING/DONE/FAILED)
    ├── logs/                          # Execution logs
    │   └── YYYY-MM-DD-ABBR.log
    └── .orchestrator.pid              # Daemon PID file
```

### 8.2 Process Architecture

```mermaid
graph TB
    USER[User Terminal] -->|duckyai -o| DAEMON[Orchestrator Daemon Process]

    DAEMON --> FM_THREAD[FileMonitor Thread]
    DAEMON --> CRON_THREAD[CronScheduler Thread]
    DAEMON --> POLL_THREAD[PollerManager Thread]
    DAEMON --> EVENT_LOOP[Main Event Loop Thread]

    EVENT_LOOP -->|spawn| AGENT1[Agent Subprocess 1]
    EVENT_LOOP -->|spawn| AGENT2[Agent Subprocess 2]
    EVENT_LOOP -->|spawn| AGENT3[Agent Subprocess 3]

    AGENT1 --> AI1[claude-code CLI]
    AGENT2 --> AI2[copilot SDK]
    AGENT3 --> AI3[gemini CLI]

    DAEMON -->|write| PID[.orchestrator.pid]
    DAEMON -->|hot reload| CONFIG[duckyai.yml]
```

---

## 9. Integration Points

### 9.1 Microsoft Teams

```mermaid
graph LR
    GRAPH[Microsoft Graph API] -->|WorkIQ MCP| TCS[TCS Agent]
    GRAPH -->|WorkIQ MCP| TMS[TMS Agent]
    TCS -->|appendTeamsChatHighlights| DN[Daily Note]
    TMS -->|appendTeamsMeetingHighlights| DN
    TMS -->|createMeeting| MN[Meeting Notes]
    TCS -->|personNotes| CN[Contact Notes]
    TMS -->|personNotes| CN

    STATE[Watermark State] <-->|get/update| TCS
    STATE <-->|get/update| TMS
```

### 9.2 VS Code / Copilot

```mermaid
graph TB
    VSCODE[VS Code] --> COPILOT[GitHub Copilot]
    COPILOT -->|reads| INSTR[.github/copilot-instructions.md]
    COPILOT -->|discovers| SKILLS[.github/skills/]
    COPILOT -->|executes| PROMPTS[.github/prompts/]
    COPILOT <-->|stdio| MCP_SRV[MCP Server - node dist/index.js]
    MCP_SRV <-->|read/write| VAULT[Vault Files]

    VSCODE -->|mcp.json config| MCP_SRV
```

---

## 10. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Orchestrator** | Python 3.8+, Click, watchdog, croniter | Daemon, CLI, file monitoring, scheduling |
| **MCP Server** | TypeScript, Node.js, @modelcontextprotocol/sdk, Zod | Vault tools for AI assistants |
| **AI Executors** | Claude Code SDK, Copilot SDK, Gemini CLI | Agent execution backends |
| **Desktop App** | Tauri 2.x (Rust + TypeScript) | Native wrapper (in development) |
| **Vault** | Obsidian + Periodic Notes + Templater + Dataview | Note-taking and knowledge management |
| **Configuration** | YAML (duckyai.yml), JSON (version.json, mcp.json) | System configuration |
| **State** | JSON files in `~/.duckyai/` | Watermarks, PID, task tracking |

---

## 11. Design Principles

1. **Markdown-First:** All data is plain markdown with YAML frontmatter — portable, version-controllable, human-readable
2. **Event-Driven:** File changes and cron schedules drive all automation — no polling loops for vault content
3. **Decoupled Components:** Orchestrator, MCP server, and CLI work independently — failure in one doesn't break others
4. **Multi-Executor:** Supports swapping AI backends (Claude, Copilot, Gemini) per agent — enables comparison and resilience
5. **Persistent Context:** The vault itself is the AI's memory — every note, task, and meeting enriches future interactions
6. **Hot-Reloadable:** Config changes to `duckyai.yml` are detected and applied without daemon restart
7. **Auditable:** Every agent execution creates a task file with status, timing, and error information
8. **Template-Based Updates:** Vault infrastructure can be updated from a template repo without touching personal content

---

## 12. Directory Map (Complete)

```
DuckyAI/
├── .github/
│   ├── copilot-instructions.md        # AI system context
│   ├── prompts/                       # 7 interactive Copilot prompts
│   ├── prompts-agent/                 # Agent system prompts (orchestrator)
│   ├── skills/                        # 21 Copilot skills (SKILL.md each)
│   └── bases/                         # Base configurations
├── .obsidian/                         # Obsidian vault config
├── .repos/                            # Cloned documentation repos (context)
├── .vscode/                           # VS Code settings + mcp.json
├── 00-Inbox/                          # Quick capture
├── 01-Work/
│   ├── Tasks/                         # Active tasks (P0-P3)
│   ├── Projects/                      # Multi-task initiatives
│   ├── Investigations/                # Technical deep-dives
│   └── Plans/                         # Roadmaps
├── 02-People/
│   ├── 1-on-1s/                       # Recurring 1:1 notes
│   ├── Meetings/                      # Meeting notes
│   └── Contacts/                      # People profiles
├── 03-Knowledge/
│   ├── Documentation/                 # Enriched documents
│   └── Topics/                        # Auto-generated topic indexes
├── 04-Periodic/
│   ├── Daily/                         # Daily notes (YYYY-MM-DD.md)
│   └── Weekly/                        # Weekly reviews
├── 05-Archive/                        # Completed items
├── Templates/                         # 9 Obsidian templates
├── cli/
│   ├── duckyai_cli/                   # Python CLI + Orchestrator
│   │   ├── main/                      # CLI commands (Click)
│   │   ├── orchestrator/              # Daemon subsystem
│   │   ├── pollers/                   # External data pollers
│   │   └── voice/                     # Voice interaction
│   └── mcp-server/                    # TypeScript MCP server
│       ├── src/index.ts               # 19 MCP tools (~1300 lines)
│       └── package.json               # Node.js dependencies
├── desktop/                           # Tauri desktop app
├── scripts/
│   └── sync-repos.ps1                 # Clone documentation repos
├── duckyai.yml                        # Master orchestrator config
├── version.json                       # Template version tracking
├── DuckyAI.code-workspace             # VS Code workspace
├── AGENTS.md                          # AI agent rules
├── GETTING_STARTED.md                 # Onboarding guide
└── README.md                          # Project overview
```
