# AI Engineering: Learn-by-Building Roadmap

## Our project

We will evolve **Agent Studio** into a production-style AI engineering platform. Each topic will
be learned just before we implement it in the application. We will keep every milestone small,
testable, and usable.

## How we will work

For every milestone, we will follow the same loop:

1. Learn the core idea in plain language.
2. Build the smallest version ourselves so the mechanics are visible.
3. Use the appropriate framework and compare it with our version.
4. Add tests and measure quality, cost, and latency.
5. Integrate it into Agent Studio and document what we learned.

## Learning and implementation path

### 0. Foundations and baseline

**Learn**

- How LLMs predict tokens; tokens, context windows, and model inputs/outputs
- System, user, assistant, and tool messages
- Temperature, structured output, streaming, latency, and token-based cost
- Embeddings versus generative models
- Python typing, async APIs, environment variables, and safe secret handling

**Implement**

- Run the existing web and API applications locally
- Trace one request from UI to model and back
- Add a token counter and prompt preview
- Record input tokens, output tokens, latency, model, and estimated cost for each run

**Done when:** one agent run is visible end-to-end with reliable usage metadata.

### 1. LLM application fundamentals without frameworks

**Learn**

- Prompt design, few-shot examples, output schemas, and validation
- Tool/function calling and the agent loop
- Retries, timeouts, rate limits, error handling, and model-provider abstraction
- Why agents fail: ambiguous instructions, invalid tool calls, and runaway loops

**Implement**

- Build a minimal model client and tool-calling loop using provider SDKs
- Add structured outputs with validation and repair
- Add execution limits, retry policy, and useful traces
- Test deterministic pieces without making paid model calls

**Done when:** an agent can safely choose tools and return schema-valid output.

### 2. Tokenization and context engineering

**Learn**

- Byte-pair encoding intuition and why different models count text differently
- Context budgeting, truncation, prompt caching, and the “lost in the middle” problem
- Conversation history, summarization, and short-term memory

**Implement**

- An interactive tokenizer/context-budget view
- Preflight checks that prevent context overflow
- Configurable history trimming and summarization
- Tests for very large prompts and documents

**Done when:** the platform predicts and controls context use before a request is sent.

### 3. RAG from first principles

**Learn**

- The RAG pipeline: ingest, parse, clean, chunk, embed, index, retrieve, rerank, generate
- Chunk-size/overlap tradeoffs and metadata filtering
- Vector similarity, cosine distance, sparse search, hybrid retrieval, and reranking
- Citations, grounded answers, and common retrieval failure modes

**Implement**

- Document ingestion with stable document and chunk identifiers
- A simple in-memory retrieval baseline
- Persistent vector storage using PostgreSQL/pgvector where practical
- Semantic, keyword, and hybrid search
- Source citations in answers and a retrieval-debug screen

**Done when:** users can upload documents, ask questions, inspect retrieved chunks, and verify citations.

### 4. RAG evaluation and improvement

**Learn**

- Retrieval metrics: recall@k, precision@k, MRR, and nDCG
- Answer metrics: correctness, faithfulness, relevance, and citation quality
- Golden datasets, synthetic questions, LLM-as-judge limits, and human review
- Offline evaluation versus production monitoring

**Implement**

- A versioned evaluation dataset
- Automated retrieval and answer evaluation
- Side-by-side experiments for chunking, embeddings, prompts, and rerankers
- Regression gates so changes cannot silently reduce quality

**Done when:** RAG changes are selected using measured evidence rather than intuition.

### 5. LangChain

**Learn**

- Models, prompt templates, messages, tools, retrievers, output parsers, and runnables
- Composition with LCEL and callbacks/tracing
- When LangChain reduces work and when direct SDK code is clearer

**Implement**

- Rebuild one existing model pipeline with LangChain
- Wrap our retriever as a LangChain retriever
- Compare framework and framework-free versions for clarity, behavior, and overhead

**Done when:** we can deliberately choose between LangChain and direct provider SDKs.

### 6. LangGraph and stateful agents

**Learn**

- Graph state, nodes, edges, conditional routing, reducers, and checkpoints
- Cycles, interrupts, human approval, resumability, and durable execution
- Multi-agent patterns and when a single agent is enough

**Implement**

- A LangGraph research workflow: plan, retrieve, use tools, draft, verify, and answer
- Checkpointing and resume-after-failure
- Human approval for sensitive tool actions
- Bounded loops and explicit termination conditions
- A graph/run visualization in Agent Studio

**Done when:** a failed or paused workflow can resume safely without repeating completed work.

### 7. Memory and advanced retrieval

**Learn**

- Short-term state versus long-term memory
- Semantic, episodic, and user-profile memory
- Query rewriting, multi-query retrieval, parent-child chunks, and contextual compression
- Memory privacy, deletion, retention, and poisoning risks

**Implement**

- Opt-in conversation and user memory with clear scope
- Memory extraction, retrieval, editing, and deletion
- Advanced retrieval experiments only when evaluation shows a benefit

**Done when:** memory is useful, inspectable, reversible, and isolated per user.

### 8. Production AI engineering

**Learn**

- Observability, traces, logs, metrics, feedback, and incident debugging
- Caching, batching, queues, concurrency, fallbacks, and model routing
- Prompt injection, data leakage, unsafe tools, SSRF, tenant isolation, and permissions
- Testing stochastic systems: unit, contract, integration, evaluation, and load tests
- Deployment, CI/CD, migrations, feature flags, and rollback

**Implement**

- End-to-end traces with prompt/version metadata and redaction
- Budgets for tokens, money, time, and tool calls
- Background jobs for ingestion and long-running workflows
- Security tests for retrieval and tool use
- Production dashboards, alerts, feedback capture, and deployment checks

**Done when:** the system is measurable, secure, economical, and recoverable in production.

## Capstone

Build a **grounded research agent** inside Agent Studio that:

- accepts private documents and a user question;
- plans a research workflow with LangGraph;
- retrieves through evaluated hybrid RAG;
- uses approved tools where needed;
- produces a structured answer with verifiable citations;
- pauses for human approval before sensitive actions;
- exposes its trace, retrieved evidence, token usage, latency, and cost;
- resumes after interruption and is covered by regression evaluations.

## Milestone scorecard

We will not call a feature complete until it has:

- a plain-language explanation of the concept;
- working code integrated into Agent Studio;
- automated tests;
- at least one measurable quality criterion;
- cost and latency visibility;
- security and failure-case notes;
- a short lesson log describing decisions and tradeoffs.

## First session

1. Run the current application and map the existing agent execution flow.
2. Send one minimal LLM request and inspect its messages and raw response.
3. Learn how that text becomes tokens.
4. Add token, latency, and cost tracking to the run trace.
5. Test the new behavior and record the first lesson log.
