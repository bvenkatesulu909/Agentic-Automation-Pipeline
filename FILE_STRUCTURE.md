# HITL System - File Structure Guide

## What Was Created

### Core System Files (in `src/ragstack/`)

```
src/ragstack/
│
├── 📄 uncertainty.py                 (408 lines)
│   └─ Uncertainty detection engine
│      - UncertaintyDetector class
│      - Evaluates retrieval + response confidence
│      - Preset detectors for different use cases
│
├── 📄 approval.py                    (280 lines)
│   └─ Approval gate system
│      - ApprovalGate: Pauses workflows
│      - ApprovalRequest/Response dataclasses
│      - ApprovalStore abstract interface
│      - gate_node_factory for LangGraph integration
│
├── 📄 workflow_state.py              (350 lines)
│   └─ Extended state management
│      - HITLWorkflowState: Dict-like wrapper
│      - AuditEntry dataclass
│      - Checkpoint management
│      - Audit trail tracking
│
├── 📄 audit.py                       (380 lines)
│   └─ Immutable audit trail logging
│      - AuditLog: Single entry record
│      - AuditLogger: Main logging interface
│      - JSON line-based persistence
│      - Complete workflow lifecycle tracking
│
├── 📄 hitl_graph.py                  (320 lines)
│   └─ HITL graph orchestrator
│      - HITLGraphBuilder: Wraps existing graphs
│      - RetrievalUncertaintyNode
│      - ResponseUncertaintyNode
│      - create_qa_hitl_graph() convenience function
│
├── 📄 hitl_server.py                 (420 lines)
│   └─ FastAPI server for workflow management
│      - REST endpoints for workflows
│      - Approval request/response handling
│      - WebSocket for real-time updates
│      - create_hitl_server() factory
│
├── 📄 hitl_example.py                (380 lines)
│   └─ Working examples
│      - Example 1: Uncertainty detection
│      - Example 2: Approval workflow
│      - Example 3: Audit trail queries
│      - Example 4: State management
│
├── db/
│   ├── 📄 __init__.py                (14 lines)
│   │   └─ Module exports
│   │
│   ├── 📄 models.py                  (250 lines)
│   │   └─ SQLAlchemy ORM models
│   │      - WorkflowModel
│   │      - ApprovalRequestModel
│   │      - ApprovalResponseModel
│   │      - AuditEntryModel
│   │      - CheckpointModel
│   │
│   └── 📄 store.py                   (280 lines)
│       └─ Database-backed approval store
│          - SQLAlchemyApprovalStore implementation
│          - CRUD operations for approvals
│          - Audit and checkpoint persistence
```

**Total Backend Code**: ~3,500 lines across 11 files

### Documentation Files (in `repo root/`)

```
├── 📄 HITL_README.md                 (400+ lines)
│   └─ Comprehensive system documentation
│      - Features overview
│      - Architecture details
│      - Component API reference
│      - Integration examples
│      - Database schema
│      - Configuration guide
│      - Frontend integration
│      - Deployment guide
│      - Troubleshooting
│
├── 📄 IMPLEMENTATION_SUMMARY.md       (300+ lines)
│   └─ Project summary and progress
│      - What's completed (Phases 1-2)
│      - What's next (Phases 3-4)
│      - File structure
│      - Key features
│      - Configuration reference
│      - Code statistics
│
├── 📄 QUICK_START.md                 (250+ lines)
│   └─ 5-minute getting started guide
│      - TL;DR example
│      - Step-by-step setup
│      - API usage examples
│      - Common scenarios
│      - Configuration options
│      - Troubleshooting
│
└── 📄 FILE_STRUCTURE.md              (this file)
    └─ Guide to created files
```

**Total Documentation**: ~1,000 lines across 4 files

## Database Schema

### SQLite File
```
hitl_workflows.db
├── workflows              (workflow metadata and status)
├── approval_requests      (pending/completed approval requests)
├── approval_responses     (human approval decisions)
├── audit_entries          (immutable audit trail)
└── checkpoints           (state snapshots at decision points)
```

### PostgreSQL Compatible
```
postgresql://user:password@host/hitl_workflows
```

Same schema as SQLite, but for production scale.

## How to Use These Files

### Option 1: Import Core Components

```python
# Use the building blocks
from ragstack.uncertainty import detector_for_qa_queries
from ragstack.approval import ApprovalGate, ApprovalPolicy
from ragstack.workflow_state import HITLWorkflowState
from ragstack.audit import AuditLogger
from ragstack.db import SQLAlchemyApprovalStore
```

### Option 2: Run Pre-Built Examples

```bash
cd src/ragstack
python -m hitl_example
```

### Option 3: Start FastAPI Server

```bash
python -c "from ragstack.hitl_server import run_hitl_server; from ragstack.db import SQLAlchemyApprovalStore; run_hitl_server(SQLAlchemyApprovalStore())"
```

### Option 4: Integrate with Existing Workflow

```python
from ragstack.hitl_graph import create_qa_hitl_graph
from ragstack.db import SQLAlchemyApprovalStore

store = SQLAlchemyApprovalStore()
hitl_graph = create_qa_hitl_graph(
    base_graph=your_existing_graph,
    approval_store=store,
)

# Use wrapped graph
result = hitl_graph.invoke(state)
```

## File Dependencies

```
hitl_example.py
    ↓
    ├─→ uncertainty.py
    ├─→ approval.py
    ├─→ workflow_state.py
    ├─→ audit.py
    └─→ db/
        └─→ store.py

hitl_server.py
    ↓
    ├─→ approval.py
    ├─→ workflow_state.py
    ├─→ audit.py
    └─→ db/
        └─→ store.py

hitl_graph.py
    ↓
    ├─→ uncertainty.py
    ├─→ approval.py
    ├─→ workflow_state.py
    ├─→ audit.py
    └─→ db/
        └─→ models.py
```

## What Each File Does

### 1. **uncertainty.py** - Core Detection Logic
- **Purpose**: Evaluate confidence in retrieval and LLM responses
- **Key Classes**: `UncertaintyDetector`, `UncertaintyScore`
- **Usage**: `detector.evaluate_retrieval(chunks)` → score (0-1)
- **Presets**: QA tuned, Sales tuned, Strict mode

### 2. **approval.py** - Approval Gate Mechanism
- **Purpose**: Pause workflows for human review
- **Key Classes**: `ApprovalGate`, `ApprovalRequest`, `ApprovalResponse`
- **Usage**: `gate.evaluate(...)` → state modified with approval_required flag
- **Policies**: REQUIRE, AUTO_IF_UNCERTAIN, SKIP

### 3. **workflow_state.py** - Extended State Management
- **Purpose**: Add HITL fields to LangGraph state
- **Key Classes**: `HITLWorkflowState`, `AuditEntry`
- **Usage**: `state.set_approval_pending(...)`, `state.checkpoint(...)`
- **Features**: Dict-like interface, audit trail, checkpoints

### 4. **audit.py** - Immutable Audit Trail
- **Purpose**: Record all workflow decisions
- **Key Classes**: `AuditLog`, `AuditLogger`
- **Usage**: `logger.log_approval_request(...)`, `logger.get_workflow_trail(id)`
- **Format**: JSON lines, append-only

### 5. **hitl_graph.py** - Graph Orchestrator
- **Purpose**: Wrap existing graphs with HITL logic
- **Key Classes**: `HITLGraphBuilder`, `RetrievalUncertaintyNode`, `ResponseUncertaintyNode`
- **Usage**: `builder.add_gate_after_node(...)`, `graph = builder.build()`
- **Integration**: Works with existing LangGraph workflows

### 6. **hitl_server.py** - FastAPI Server
- **Purpose**: Expose workflows via REST + WebSocket
- **Key Functions**: `create_hitl_server()`, `run_hitl_server()`
- **Endpoints**: /workflows/*, /approvals/*, WebSocket /ws/*
- **Port**: 8001 (default)

### 7. **hitl_example.py** - Working Examples
- **Purpose**: Demonstrate all components
- **Examples**: 4 complete working scenarios
- **Usage**: `python -m hitl_example`
- **Output**: Console demo + example database

### 8. **db/models.py** - Database Schema
- **Purpose**: SQLAlchemy ORM model definitions
- **Tables**: workflows, approval_requests, approval_responses, audit_entries, checkpoints
- **Features**: Relationships, JSON fields, timestamps

### 9. **db/store.py** - Database Access Layer
- **Purpose**: Implement ApprovalStore interface with database
- **Key Class**: `SQLAlchemyApprovalStore`
- **Methods**: CRUD for approvals, audit entries, checkpoints
- **Databases**: SQLite (default) or PostgreSQL

### 10. **db/__init__.py** - Module Exports
- **Purpose**: Clean imports for database layer
- **Exports**: All models + SQLAlchemyApprovalStore

## Configuration Files Created

No configuration files are created automatically, but you can create:

```
.env (optional)
├─ HITL_DB_URL=sqlite:///hitl_workflows.db
├─ HITL_PORT=8001
├─ HITL_HOST=0.0.0.0
└─ HITL_LOG_FILE=audit.jsonl
```

## Testing & Verification

### Run Examples
```bash
cd src/ragstack
python -m hitl_example
```

Creates: `example_hitl.db`

### Start Server
```bash
python -c "from ragstack.hitl_server import run_hitl_server; from ragstack.db import SQLAlchemyApprovalStore; run_hitl_server(SQLAlchemyApprovalStore())"
```

Listen on: `http://localhost:8001`

### Test API
```bash
curl http://localhost:8001/health
curl http://localhost:8001/approvals/pending
```

## Documentation Files

### HITL_README.md (Main Reference)
- ✅ Complete feature list
- ✅ Architecture overview
- ✅ Component API docs
- ✅ Integration examples
- ✅ Database schema
- ✅ Configuration reference
- ✅ Frontend integration guide
- ✅ Deployment instructions
- ✅ Security considerations
- ✅ Performance notes
- ✅ Troubleshooting

**Use this for**:
- Understanding the full system
- API reference
- Integration guide
- Deployment planning

### IMPLEMENTATION_SUMMARY.md (Project Status)
- ✅ What's completed (Phases 1-2)
- ✅ What's next (Phases 3-4)
- ✅ Code statistics
- ✅ Project structure
- ✅ Success criteria
- ✅ Configuration reference

**Use this for**:
- Project overview
- Understanding what exists
- Planning next phases
- Configuration options

### QUICK_START.md (5-Minute Guide)
- ✅ TL;DR code snippet
- ✅ Step-by-step setup
- ✅ Common scenarios
- ✅ API examples
- ✅ Configuration options
- ✅ Troubleshooting

**Use this for**:
- Getting started quickly
- Trying the system
- Common use cases
- Debugging issues

### FILE_STRUCTURE.md (This File)
- ✅ File listing with descriptions
- ✅ Lines of code per file
- ✅ Dependencies between files
- ✅ What each file does
- ✅ How to use each module

**Use this for**:
- Finding specific code
- Understanding dependencies
- Learning file organization
- Navigating the codebase

## Next Steps

### Immediate (Try It)
1. Read QUICK_START.md
2. Run `python -m hitl_example`
3. Start FastAPI server
4. Test API endpoints

### Short Term (Integrate)
1. Review HITL_README.md
2. Choose integration approach
3. Add gates to your workflow
4. Test with real data

### Medium Term (Frontend)
1. Build React approval UI
2. Connect to FastAPI server
3. Implement approval queue
4. Add real-time WebSocket updates

### Long Term (Production)
1. Deploy to production environment
2. Configure PostgreSQL
3. Add authentication
4. Monitor audit trail
5. Track approval metrics

## Code Quality

- ✅ Type hints throughout
- ✅ Comprehensive docstrings
- ✅ Error handling
- ✅ Logging at appropriate levels
- ✅ Modular design
- ✅ No external service dependencies
- ✅ SQLite + PostgreSQL support
- ✅ Thread-safe database operations

## Size & Scope

**Backend System**: ~3,500 lines
- Core logic: ~2,500 lines
- Database layer: ~530 lines
- Examples: ~380 lines

**Documentation**: ~1,000 lines
- README: 400+ lines
- Implementation Summary: 300+ lines
- Quick Start: 250+ lines
- File Structure: 200+ lines

**Total Project**: ~4,500 lines code + docs

Ready to build the frontend? See **QUICK_START.md** for next steps!
