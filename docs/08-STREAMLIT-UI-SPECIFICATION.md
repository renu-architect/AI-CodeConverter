# Streamlit UI Specification

## App Structure

```
frontend/
├── app.py                    # Main entry, sidebar navigation
├── pages/
│   ├── 1_Dashboard.py
│   ├── 2_Repository.py
│   ├── 3_Migration_Plan.py
│   ├── 4_Live_Execution.py
│   ├── 5_History.py
│   ├── 6_Knowledge.py
│   └── 7_Settings.py
├── components/
│   ├── progress_bar.py
│   ├── cost_display.py
│   ├── artifact_viewer.py
│   ├── log_stream.py
│   └── approval_form.py
└── state.py                  # Session state management
```

## Run Command
```bash
streamlit run frontend/app.py
```

---

## Page 1: Dashboard

### Layout
```
┌─────────────────────────────────────────────────┐
│  AI-SDLC Framework                    [Settings]│
├─────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Total    │ │ Success  │ │ Avg Cost │        │
│  │ Jobs: 24 │ │ Rate:92% │ │ $0.35    │        │
│  └──────────┘ └──────────┘ └──────────┘        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ Tokens   │ │ Avg Time │ │ Patterns │        │
│  │ 1.2M     │ │ 32 min   │ │ Reused:45│        │
│  └──────────┘ └──────────┘ └──────────┘        │
│                                                 │
│  Current Job (if running)                       │
│  ┌─────────────────────────────────────────┐    │
│  │ Job: customer_etl  Stage: REVIEWING     │    │
│  │ ████████████░░░░ 72%  Agent: Reviewer   │    │
│  │ Tokens: 32K  Cost: $0.28  Time: 18min  │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  Recent Migrations                              │
│  ┌─────────────────────────────────────────┐    │
│  │ Date       Job          Score  Status   │    │
│  │ 2026-07-25 customer_etl  92   ✓        │    │
│  │ 2026-07-24 orders_etl      88   ✓        │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### Data Sources
- `MetricsService.get_dashboard_metrics()` → SQLite aggregates
- `Orchestrator.get_status(workflow_id)` → current running job

### Components
- `st.metric()` for KPI cards
- `st.progress()` for running job
- `st.dataframe()` for recent migrations

---

## Page 2: Repository Selection

### Layout
```
┌─────────────────────────────────────────────────┐
│  Repository Selection                           │
├─────────────────────────────────────────────────┤
│  Source Type: (•) Local Folder  ( ) Git URL     │
│                                                 │
│  Path: [________________________] [Browse]        │
│                                                 │
│  Scope:                                         │
│  ( ) Single Job                                 │
│  (•) Multiple Jobs                              │
│  ( ) Entire Repository                          │
│                                                 │
│  Detected Glue Jobs:                            │
│  ┌─────────────────────────────────────────┐    │
│  │ ☑ customer_etl.py     Complexity: 72    │    │
│  │ ☑ orders_etl.py       Complexity: 45    │    │
│  │ ☐ inventory_etl.py    Complexity: 88    │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  [Scan Repository]  [Start Migration →]         │
└─────────────────────────────────────────────────┘
```

### Behavior
1. User selects path → clicks "Scan Repository"
2. Call `RepositoryScanner.scan()` → display detected jobs
3. User selects jobs → clicks "Start Migration"
4. Call `Orchestrator.start_workflow()` → navigate to Migration Plan page

### Session State
```python
st.session_state.repo_path: str
st.session_state.scan_result: ProjectScan | None
st.session_state.selected_jobs: list[str]
st.session_state.workflow_id: str | None
```

---

## Page 3: Migration Plan

### Layout
```
┌─────────────────────────────────────────────────┐
│  Migration Plan: customer_etl                   │
├─────────────────────────────────────────────────┤
│  [Understanding] [Plan] [Risks] [Cost]          │
│                                                 │
│  Tab: Plan                                      │
│  ┌─────────────────────────────────────────┐    │
│  │ ## Migration Steps                       │    │
│  │ 1. Replace GlueContext...               │    │
│  │ 2. Convert DynamicFrame...              │    │
│  │ ...                                      │    │
│  │                                          │    │
│  │ ## API Mapping                           │    │
│  │ | Glue API | Synapse API |              │    │
│  │ ...                                      │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  Cost Estimate                                  │
│  Tokens: ~20,000  Cost: ~$0.18  Time: ~45min   │
│                                                 │
│  Comments: [________________________]           │
│  [Approve ✓]  [Reject ✗]  [Modify Plan]        │
└─────────────────────────────────────────────────┘
```

### Behavior
- Display artifacts from Analyzer and Planner stages
- Tabs: Understanding.md, MigrationPlan.md, Risks, Cost Estimate
- Approve → `Orchestrator.approve_plan(workflow_id, True)`
- Reject → `Orchestrator.approve_plan(workflow_id, False)` → back to repo
- On approve → navigate to Live Execution

### Component: `artifact_viewer.py`
```python
def render_artifact(content: str, artifact_type: str) -> None:
    """Render markdown artifact with syntax highlighting."""
    st.markdown(content)
```

---

## Page 4: Live Execution

### Layout
```
┌─────────────────────────────────────────────────┐
│  Live Execution: customer_etl                     │
├─────────────────────────────────────────────────┤
│  Stage: REVIEWING          Iteration: 2         │
│  ████████████████░░░░ 80%                        │
│                                                 │
│  Current Agent: Reviewer                        │
│  Current File: customer_etl_synapse.py          │
│  Elapsed: 22:15    Remaining: ~8:00             │
│                                                 │
│  Tokens: 32,400    Cost: $0.31                  │
│                                                 │
│  ┌─ Logs ─────────────────────────────────┐     │
│  │ 10:22:15 [REVIEWER] Starting review...  │     │
│  │ 10:22:18 [REVIEWER] Check: business ✓   │     │
│  │ 10:22:20 [REVIEWER] Check: output ✗    │     │
│  │ 10:22:21 [REVIEWER] Failed: partition   │     │
│  │ 10:22:22 [ORCH] Returning to implementer│     │
│  └─────────────────────────────────────────┘     │
│                                                 │
│  [Abort Migration]                              │
└─────────────────────────────────────────────────┘
```

### Behavior
- Poll `Orchestrator.get_status()` every 2 seconds
- Subscribe to `WorkflowEvent` stream for logs
- Auto-navigate to History on COMPLETE
- Abort button calls `Orchestrator.abort_workflow()`

### Component: `log_stream.py`
```python
def render_log_stream(workflow_id: str, container) -> None:
    """Auto-scrolling log display from workflow events."""
```

---

## Page 5: History

### Layout
```
┌─────────────────────────────────────────────────┐
│  Migration History                              │
│  Filter: [Date Range] [Project] [Status]        │
├─────────────────────────────────────────────────┤
│  Date        Job           Dev    Score  Tokens │
│  2026-07-25  customer_etl  john   92    45K   │
│  2026-07-24  orders_etl     jane   88    32K   │
│                                                 │
│  Selected: customer_etl (2026-07-25)             │
│  Iterations: 2 implement, 2 review              │
│  Duration: 45 min  Cost: $0.42                  │
│  [Download Package]  [View Artifacts]           │
└─────────────────────────────────────────────────┘
```

### Download Package
ZIP containing full output package per artifact spec.

---

## Page 6: Knowledge

### Layout
```
┌─────────────────────────────────────────────────┐
│  Knowledge Base                                 │
│  Search: [Glue Catalog bookmark migration___]   │
├─────────────────────────────────────────────────┤
│  Quick Filters:                                 │
│  [Glue Catalog] [Bookmarks] [ResolveChoice]     │
│  [ApplyMapping] [DynamicFrame]                    │
│                                                 │
│  Results:                                       │
│  ┌─────────────────────────────────────────┐    │
│  │ ★ Bookmark → Delta MERGE (confidence:0.95)│
│  │   Used in 3 migrations. Pattern: ...     │    │
│  │ ★ ApplyMapping → select/alias (0.92)    │    │
│  │   Used in 8 migrations. Pattern: ...     │    │
│  └─────────────────────────────────────────┘    │
│                                                 │
│  Developer Corrections:                         │
│  ┌─────────────────────────────────────────┐    │
│  │ 2026-07-20: Fixed join type in orders   │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### Data Source
- `KnowledgeEngine.retrieve(query, collection, top_k)`
- `KnowledgeEngine.get_corrections()`

---

## Page 7: Settings

### Fields
| Setting | Type | Default |
|---------|------|---------|
| Claude API Key | password input | from env |
| Model | selectbox | claude-sonnet-4-20250514 |
| Embedding Model | text | all-MiniLM-L6-v2 |
| Temperature | slider (locked 0) | 0.0 |
| Max Context Tokens | number | 8000 |
| Max Output Tokens | number | 4096 |
| Cache Enabled | checkbox | true |
| Cache TTL (hours) | number | 24 |
| Log Level | selectbox | INFO |
| Langfuse Enabled | checkbox | false |
| Langfuse Public Key | text | from env |
| Langfuse Secret Key | password | from env |

### Behavior
- Settings saved to `config/user.yaml` (not committed to git)
- API keys read from env vars first, UI override second
- Never persist API keys to SQLite

---

## Session State Schema

```python
# frontend/state.py

@dataclass
class AppState:
    workflow_id: str | None = None
    project_id: str | None = None
    repo_path: str | None = None
    scan_result: ProjectScan | None = None
    selected_jobs: list[str] = field(default_factory=list)
    current_page: str = "dashboard"
    settings: dict = field(default_factory=dict)

def init_session_state() -> None:
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState()
```

---

## Navigation

Sidebar:
```
🏠 Dashboard
📁 Repository
📋 Migration Plan     (disabled until workflow started)
⚡ Live Execution     (disabled until approved)
📜 History
🧠 Knowledge
⚙️ Settings
```

Pages enabled/disabled based on workflow state.
