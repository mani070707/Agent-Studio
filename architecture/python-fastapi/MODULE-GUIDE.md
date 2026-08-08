# Module Guide

Add business behaviour in this order:

1. Model invariants as domain values or policies.
2. Define repository/provider protocols required by the use case.
3. Implement a class-based application service.
4. Implement SQLAlchemy or external-service adapters.
5. Expose a thin FastAPI route with Pydantic request/response models.
6. Test domain logic, tenant isolation, adapter failures and the HTTP contract.

Do not query another module's tables from an HTTP route and do not pass API keys into DTOs,
exceptions, logs or traces. Built-in catalogs belong in code rather than startup seed routines.
