# Troubleshooting

- `401`: verify Supabase issuer, audience and bearer token; local bypass needs an existing user ID.
- `503 /ready`: confirm `DATABASE_URL`, network access and Supabase project state.
- Provider validation failure: test the saved connection; keys and provider bodies are redacted.
- Frontend cannot reach API: set `API_PROXY_TARGET=http://localhost:8000` and restart Next.js.
- Existing database reports duplicate tables: stamp `0001_existing_schema` instead of upgrading it.
- Fresh database lacks `auth` or `storage`: create the Supabase project before running the baseline.
