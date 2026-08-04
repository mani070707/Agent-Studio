# Agent Studio — Java 17 / Spring Boot Architecture

This directory is the proposed architecture for replacing the FastAPI backend with a Java 17
Spring Boot backend while retaining the current Next.js frontend and Supabase infrastructure.

## Documents

- [HLD.md](HLD.md) — system context, containers, deployment, scaling, availability, security,
  reliability, traffic scenarios, and service-level objectives.
- [LLD.md](LLD.md) — modules, packages, ports and adapters, data ownership, APIs, job state
  machines, agent execution, RAG, events, transactions, testing, and configuration.
- [MIGRATION-PLAN.md](MIGRATION-PLAN.md) — incremental FastAPI-to-Spring-Boot strangler migration
  with compatibility gates and rollback at every phase.

## Architecture decision

Use a **modular monolith with independently deployable API and worker processes**.

This is not a distributed monolith and not a permanent restriction. Module boundaries are kept
strict through Spring Modulith, package visibility, module tests, domain events, and explicit
ports. A module can later be extracted into a service when traffic, team ownership, data isolation,
or failure isolation proves the need.

## Fixed technology choices

| Concern | Choice |
|---|---|
| Language | Java 17 |
| Application | Spring Boot 3.5.16 (Java 17 baseline) |
| Module boundaries | Spring Modulith |
| HTTP | Spring MVC for CRUD; WebFlux/SSE only for streaming endpoints |
| Security | Spring Security OAuth2 Resource Server, Supabase JWT/JWKS |
| Persistence | Spring Data JPA, PostgreSQL, Flyway |
| AI abstraction | Spring AI 1.1.8 behind application-owned ports |
| Vector search | pgvector in PostgreSQL |
| Object storage | Supabase Storage through an application-owned port |
| Durable jobs | PostgreSQL job table + `FOR UPDATE SKIP LOCKED` initially |
| Cache/rate limits | Redis only when load requires it |
| Resilience | Resilience4j, timeouts, bounded retries, circuit breakers, bulkheads |
| Observability | Actuator, Micrometer, OpenTelemetry, structured logs |
| Tests | JUnit 5, AssertJ, Mockito, Testcontainers, WireMock |
| Build | Maven multi-module build |
