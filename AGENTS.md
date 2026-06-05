# AGENTS.md — ai-admin

Full-stack enterprise low-code platform: **FastAPI + Vue 3 (Vben Admin 5.x)**.

## Repository structure

Two independent roots at the top level:

- **`backend/`** — Python FastAPI async backend
- **`web/`** — TypeScript/Vue pnpm monorepo with Turborepo

## Backend (`backend/`)

### Prerequisites
- Python 3.12+, PostgreSQL 16+, Redis

### Setup & run
```bash
cd backend
pip install -r requirements.txt
cp env/example.env env/dev.env
# edit env/dev.env with DB credentials, etc.
alembic upgrade head
python scripts/loaddata.py db_init.json    # seed initial data (first time)
python main.py                             # starts uvicorn on :8000
```

- Config is loaded via `ENV` env var (default `dev`): reads `env/{ENV}.env`
- DB is PostgreSQL by default; set `DB_TYPE=mysql` in `.env` for MySQL
- API docs at `http://localhost:8000/docs`

### Key architecture
- **FastAPI entry**: `backend/main.py` — uses `lifespan` for startup (registers forms, warms Redis cache, starts APScheduler)
- **Routes**:
  - `/api/core/*` — core business modules (user, role, menu, dept, auth, etc.)
  - `/api/online_dev/*` — form builder, page designer
  - `/rag/*` — RAG/AI features (WebSocket at `/rag/api/ws/*`)
  - `/ws/*` — general WebSocket
- **Auth**: JWT via `AuthPermissionMiddleware` (global middleware). Whitelisted paths: login, docs, OAuth callbacks, WS, UI config prefs.
- **ORM**: SQLAlchemy 2.0 async — `AsyncSessionLocal` in `app/database.py`
- **Models**: All inherit `BaseModel` (`app/base_model.py`) — nanoid 21-char PK, soft delete (`is_deleted`), audit fields (`sys_creator_id`, etc.)
- **Service pattern**: `BaseService[Model, CreateSchema, UpdateSchema]` provides CRUD. Optional `CacheService` for Redis caching.
- **Modules** under `core/` follow: `model.py` / `schema.py` / `service.py` / `api.py`. Register API router in `core/router.py`.

### Backend directory structure
```
backend/
├── main.py                  # FastAPI entry (uvicorn, lifespan, routes)
├── requirements.txt         # Python dependencies (pinned)
├── app/                     # Core framework
│   ├── base_model.py        # BaseModel with nanoid PK, soft delete, audit
│   ├── base_service.py      # BaseService generic CRUD + Excel
│   ├── cache_service.py     # Redis caching mixin
│   ├── config.py            # pydantic-settings (reads env/{ENV}.env)
│   ├── database.py          # AsyncSessionLocal, get_db, transaction
│   └── ...                  # email, sms, dingtalk, feishu, wecom, etc.
├── core/                    # 31 business modules
│   ├── auth/ user/ role/ menu/ dept/ permission/ post/
│   ├── dict/ dict_item/ region/ application/ device/
│   ├── chat/ message/ file_manager/ websocket/
│   ├── oauth/ dingtalk_sync/ feishu_sync/ wecom_sync/
│   ├── ui_config/ system_config/ data_source/
│   ├── code_generator/ api_token/ link_preview/
│   ├── login_log/ resource_scope/
│   ├── server_monitor/ redis_monitor/ database_monitor/
│   ├── redis_manager/ database_manager/
│   └── router.py            # Aggregates all core sub-routers
├── online_dev/              # Form/Page builder (zero-code)
│   ├── form_manager/        # Form designer + published form registry
│   ├── form_data_manager/   # Form data CRUD + dynamic query
│   ├── page_manager/        # Page designer + render
│   └── router.py
├── rag/                     # Knowledge graph RAG engine
├── scheduler/               # APScheduler 4.x task management
│   ├── model.py / api.py / service.py / tasks.py
│   └── router.py
├── utils/                   # Shared utilities
│   ├── auth_middleware.py    # Global JWT auth middleware
│   ├── security.py           # JWT encode/decode
│   ├── context.py            # Request-scoped user context
│   └── redis.py              # Redis client wrapper
├── scripts/                 # Data dump/load utilities
│   ├── dumpdata.py          # python scripts/dumpdata.py -o file.json -f
│   └── loaddata.py          # python scripts/loaddata.py file.json
├── alembic/                 # Migrations (auto-imports all *model.py)
│   └── env.py               # auto_import_models() scans core/, scheduler/, online_dev/, rag/
└── env/                     # {ENV}.env config files
```

### Commands
```bash
# Migrations (run from backend/)
alembic revision --autogenerate -m "message"
alembic upgrade head
alembic downgrade -1

# Data dump/load
python scripts/dumpdata.py -o db_init.json -f
python scripts/loaddata.py db_init.json

# Start with uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Lint & format (ruff, configured in pyproject.toml)
ruff check .                       # lint all files
ruff check --fix .                 # lint + auto-fix
ruff format .                      # format all files
ruff format --check .              # check formatting without changes
```

### Creating a new backend module
```bash
mkdir core/example
touch core/example/__init__.py
touch core/example/{model,schema,service,api}.py
# Then register in core/router.py
```

## Frontend (`web/`)

### Prerequisites
- Node.js >= 20.10, pnpm >= 9.12

### Setup & run
```bash
cd web
pnpm install
pnpm dev                          # starts @vben/web-ele on :5777
```

### Key scripts (from `web/package.json`)
| Command | Purpose |
|---|---|
| `pnpm dev` | Dev server (port 5777) |
| `pnpm build` | Build all packages |
| `pnpm build:ele` | Build only `@vben/web-ele` |
| `pnpm lint` | Lint with vsh (prettier → eslint → stylelint) |
| `pnpm format` | Auto-format with prettier via vsh |
| `pnpm check:circular` | Circular dependency scan |
| `pnpm check:dep` | Dependency check |
| `pnpm check:type` | TypeScript typecheck via turbo |
| `pnpm check:cspell` | Spell check |
| `pnpm check` | circular → dep check → typecheck → cspell |
| `pnpm test:unit` | Vitest unit tests (happy-dom) |
| `pnpm test:e2e` | Playwright e2e tests |
| `pnpm commit` | Commit with czg (conventional commits) |

### App configuration
- Dev env file: `web/apps/web-ele/.env.development` (port 5777, VITE_DEVTOOLS=true)
- Prod env file: `web/apps/web-ele/.env.production`
- Vite proxy: `/basic-api` → `http://localhost:8000`, `/ws` → `ws://localhost:8000`
- Typecheck per app: `pnpm --filter @vben/web-ele run typecheck`

### Frontend architecture
- **Only one real app**: `@vben/web-ele` at `web/apps/web-ele/`
- Shared packages: `web/packages/` (utils, styles, types, locales, icons, etc.), `web/packages/@core/` (UI kit, composables), `web/packages/effects/` (layouts, hooks, plugins)
- Internal tooling: `web/internal/` (vite-config, eslint, prettier, stylelint, commitlint, tsconfig, tailwind-config)
- Entry: `web/apps/web-ele/src/main.ts` → loads backend UI config → `initPreferences` → `bootstrap()`

### Frontend directory structure
```
web/apps/web-ele/src/
├── main.ts              # App entry: get appCode → load UI config → initPreferences → bootstrap
├── bootstrap.ts         # Create Vue app, install i18n/pinia/router/adapter/plugins, mount
├── preferences.ts       # Frontend preference overrides (layout, theme, auth mode)
├── api/
│   ├── core/rag.ts      # RAG API client (853 lines: KB CRUD, graph, QA, AI writer, streaming SSE)
│   ├── core/auth.ts     # Auth/login APIs
│   └── ...              # 35+ API modules mirroring backend core modules
├── views/
│   ├── _core/rag/       # RAG views (knowledge base, graph, QA, file manager, AI writer)
│   ├── _core/chat/      # Chat views
│   ├── _core/user/ role/ menu/ dept/ ...   # CRUD views per module
│   ├── online-dev/      # Form designer, page designer
│   └── dashboard/       # Dashboard views
├── components/rag/      # Reusable RAG components (GraphVisualization, ChatArea, etc.)
├── components/zq-table/ zq-form/ zq-editor/ ...  # Shared business components
├── router/
│   ├── index.ts         # createRouter + guards
│   ├── routes/core.ts   # Core route definitions (root layout, auth, RAG, forms)
│   └── routes/modules/  # Dynamic route modules
└── adapter/             # Vben ↔ Element Plus adapter (component, form, vxe-table)
```

### Conventions
- Commits: conventional changelog via commitlint + czg (use `pnpm commit`)
- Pre-commit (lefthook): prettier → eslint → stylelint on staged files
- Post-merge: auto `pnpm install`

## Development guide: Knowledge Graph RAG

The RAG module at `backend/rag/` is a knowledge-graph-enhanced RAG system with two-tier graph (file-level + KB-level merge), LLM-based entity extraction, community detection, and streaming Q&A.

### Module layout
```
rag/
├── router.py              # Aggregates all sub-routers
├── config/                # ConfigManager singleton (Construction, Retrieval, Agent, FAISS, Embeddings)
│   ├── config_loader.py   # Dataclass-based config loaded from env
│   └── api.py             # GET/POST /api/config/ircot to toggle IRCoT mode
├── kb_manager/            # Knowledge base CRUD + file management
│   ├── model.py           # KnowledgeBase, KnowledgeBaseFile, KnowledgeBaseRole
│   └── service.py         # RBAC permission check, file upload/OCR, KB-level merge trigger
├── file_manager/          # General file system for RAG (upload, tree, rename, delete, OCR, text)
│   └── model.py           # RagFileManager (folder/file, parent_id, md5, ocr/llm status)
├── graph_manager/         # Single-file graph construction + Q&A + WebSocket progress
│   ├── model.py           # KnowledgeGraph (file_id FK, graph_data JSON, chunks_data JSON)
│   ├── service.py         # construct_file_graph_service, ask_file_question_stream (SSE)
│   └── socket_manager.py  # ConnectionManager: maps client_id→WebSocket, sends progress events
├── graph_merge/           # Multi-file graph merge (file → KB merge → community detection)
│   └── service.py         # merge_graphs_service, merge_kb_graphs_service, incremental update
├── rag_models/            # Core graph construction and retrieval algorithms
│   ├── constructor/
│   │   ├── kt_gen.py      # KTBuilder: chunk → LLM extract (entities, relations, attributes, tags)
│   │   ├── tree_comm.py   # FastTreeComm: KMeans + hierarchical merge → community detection
│   │   ├── text_chunker.py # RecursiveCharacterTextSplitter (langchain)
│   │   └── schema_manager.py # Schema evolution (agent mode: discover new types via LLM)
│   └── retriever/
│       ├── agentic_decomposer.py # GraphQ: question decomposition into sub-questions
│       ├── retrieval_core.py     # init_retrieval_state, build_FAISS, multi-path recall
│       ├── chunk_retriever.py    # Chunk-level retrieval
│       ├── path1_node_relation.py # Node+relation retrieval path
│       ├── path2_triple_only.py  # Triple-only retrieval path
│       ├── faiss_index.py        # FAISS vector index operations
│       ├── triple_scorer.py      # Triple relevance scoring
│       └── type_filter.py        # Entity type filtering
├── ai_writer/             # AI writing assistant (conversations, documents, SSE stream)
├── chat_history/          # RAG chat conversations + messages (persisted to DB)
└── utils/
    ├── call_llm_api.py    # LLMCompletionCall (sync) + LLMCompletionCallStream (async SSE)
    └── graph_processor.py # NetworkX ↔ JSON graph conversion (load_graph, save_graph)
```

### Knowledge graph construction pipeline

```
1. Upload file → KB file record (rag_knowledge_base_file)
2. POST /construct-graph (rag/graph_manager/api.py)
   └─ construct_file_graph_service()
      ├─ Text chunking: rag_models/constructor/text_chunker.py
      ├─ LLM triple extraction: rag_models/constructor/kt_gen.py
      │   → KTBuilder.build_knowledge_graph() → MultiDiGraph
      │   → entities, relations, attributes, macro_tags
      ├─ Community detection: rag_models/constructor/tree_comm.py
      │   → FastTreeComm (KMeans + hierarchical merge, LLM-named communities)
      ├─ Format output → List[triple dicts] → save to KnowledgeGraph (graph_data JSON)
      └─ AUTO: graph_merge/service.py → merge_kb_graphs_service
         → merges all files' graphs → community detection
         → saved as "merged" virtual file
```

### Graph data model (DB: `rag_knowledge_graph`)
- `file_id` (unique FK → rag_knowledge_base_file.id)
- `graph_data` JSON: `[{start_node:{label,properties}, relation, end_node:{label,properties}}]`
- `chunks_data` JSON: `{chunk_id: chunk_text}`

Graph uses triples with node levels: level1=attribute, level2=entity, level3=keyword, level4=community.

### Q&A pipeline (SSE streaming)

```
POST /ask-question → StreamingResponse (rag/graph_manager/api.py)
  1. Load graph_data + chunks_data from DB
  2. init_retrieval_state → build FAISS index for chunk embeddings
  3. GraphQ.decompose(question) → list of sub-questions
  4. For each sub-question:
       process_retrieval_results → triples + chunks + community summaries
  5. build_prompt (context = triples + chunks + summaries)
  6. Two paths:
     - Non-IRCoT: generate_answer_stream → direct answer
     - IRCoT: iterative chain-of-thought, up to max_steps, refines query
  7. SSE events: token, metadata, reasoning_steps, visualization, done
```

### Configuration
- **LLM**: `settings.LLM_MODEL`, `settings.LLM_BASE_URL`, `settings.LLM_API_KEY` (from env)
- **IRCoT**: toggle via `POST /api/config/ircot` with `{enable: bool}`
- **ConfigManager** (`rag/config/config_loader.py`): ConstructionConfig (chunk_size, overlap, mode), RetrievalConfig (top_k, recall_paths), AgentConfig (max_steps, enable_ircot)

### WebSocket progress
- `ws://host/api/ws/{client_id}?token=...` (JWT in query string)
- `ConnectionManager` sends `{type:"progress", stage, progress, message}` during graph construction
- Separate from `core/websocket/` (which handles chat, notifications, server/redis/db monitor)

### Permission model
- `rag_knowledge_base_role` table (FK to `core_role`)
- `KnowledgeBasePermissionService.check_kb_access(db, kb_id, user)` enforces role-based access
- Superusers bypass all checks
- Frontend queries `/api/knowledge-base/role/{roleId}/kb-permissions`

### Schema evolution (agent mode)
When `construction.mode == "agent"`, LLM prompt includes `new_schema_types`. If the model discovers new entity/relation/attribute types, they are merged into the file's schema via `merge_schema_types` and persisted by `update_file_schema`.

### Incremental updates
`POST /knowledge-base/{kb_id}/files/{file_id}/incremental-update` — accepts a new file, builds graph for new text only, then merges old + new graph, chunks, appends content, and triggers KB-level merge.

### Frontend RAG
- **API client**: `web/apps/web-ele/src/api/core/rag.ts` — complete TypeScript client with SSE stream handling (`askQuestionStream`, `chatCompletionStream`, `aiWritingStream`)
- **Views**: `views/_core/rag/` — dashboard, knowledge base detail, graph visualization, QA, file manager, AI writer
- **Components**: `components/rag/` — GraphVisualization, ChatArea, NodeSearchBar, EntityLegend, ThinkingProcess, AiChatPanel, NodeDetailsPanel, etc.

## Cross-cutting

- No CI workflows present in this repo.
- No Docker Compose in repo (possibly outside).
- Avoid committing `.env.*.local` files or secrets (gitignored).
- Backend sends token to frontend; frontend stores in localStorage under `vben-shared-auth-tokens` for cross-tab sync.

## Code writing standards

### [MUST] Lazy imports

Import third-party dependencies at point of use, not at file top. For base-class imports, prefer factory pattern:

```python
def get_xxx_cls() -> "MyClass":
    from xxx import BaseClass
    class MyClass(BaseClass): ...
    return MyClass
```

### [SHOULD] Conciseness

Avoid unnecessary temporary variables. Merge duplicate blocks. Prefer reusing existing utilities.

### [MUST] Encapsulation naming

- Internal module/package files use `_` prefix (e.g. `_internal.py`) and expose via `__init__.py`.
- Internal-only classes, functions, and variables must use `_` prefix.

### [MUST] Security

- Never hardcode API keys, tokens, passwords, or other secrets.
- Use environment variables, config center, or secret manager.
- No debug info, temporary credentials, or test backdoors in committed code.
- Guard against injection attacks (SQL, command, code injection, etc.).

### [MUST] Tests

New features must include adequate unit tests. Critical logic should have integration or regression test coverage.

### [MUST] Comment & docstring language

Write all comments and docstrings in **English**.

All public classes and methods must have a full docstring following this template:

```python
def func(a: str, b: int | None = None) -> str:
    """{description}

    Args:
        a (`str`):
            The argument a
        b (`int | None`, optional):
            The argument b

    Returns:
        `str`:
            The return str
    """
```

Special content may use reStructuredText or compatible doc syntax:

```python
class MyClass:
    """Example class.

    `Example link <https://xxx>`_

    .. note:: Example note

    .. tip:: Example tip

    .. important:: Example important info

    .. code-block:: python

        def hello_world():
            print("Hello world!")

    """
```

### [MUST] Pre-commit compliance

- Fix code to meet lint/typecheck requirements rather than skipping checks.
- Never suppress checks at file level.
- Only allowed exception: formatting constraints from system prompt parameters (e.g. avoiding `\n` auto-escaping).
