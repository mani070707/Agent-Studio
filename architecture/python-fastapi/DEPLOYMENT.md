# Deployment

Build `api/Dockerfile` and configure the variables documented in `api/.env.example`. Run Alembic
before starting a new release. Existing installations must stamp the baseline once; fresh projects
run `alembic upgrade head`.

The API listens on the platform-provided port (default `8000`). Configure `/health` as liveness and
`/ready` as readiness. Point the Next.js server-side proxy at the private API URL and expose only
the web application publicly where possible.

Free hosting is appropriate for learning but may sleep, throttle or pause. Production requires a
non-sleeping API instance, database backups, alerting, controlled migrations and tested recovery.
