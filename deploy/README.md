# ReBOB Hosted Deployment (IBM Code Engine)

## Prerequisites

1. IBM Cloud CLI (`ibmcloud`) logged in
2. Code Engine project created
3. Container Registry namespace for the image
4. **IBM Cloud Databases for PostgreSQL** with the `pgvector` extension enabled:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## Build and push

```bash
docker build -t us.icr.io/<namespace>/rebob:latest .
ibmcloud cr login
docker push us.icr.io/<namespace>/rebob:latest
```

## Configure secrets

Copy `deploy/.env.ce.example` and fill in values, then:

```bash
set -a && source deploy/.env.ce.example && set +a
chmod +x deploy/codeengine.sh
./deploy/codeengine.sh
```

## Issue a user token

On a machine with `DATABASE_URL` and `REBOB_ADMIN_TOKEN` set:

```bash
export REBOB_BACKEND=postgres
rebob admin issue-token --org my-team --author alice@example.com
```

## Client setup

```bash
rebob init --server https://<ce-app-url>
rebob login --token rebob_... --server-url https://<ce-app-url>
rebob register-watsonx   # BYO watsonx credentials
```

Bob MCP endpoint: `https://<ce-app-url>/mcp` (streamable-http)

Health checks: `/healthz`, `/readyz`

## Local Postgres for development

```bash
docker compose up -d
export DATABASE_URL=postgresql://rebob:rebob@localhost:5433/rebob
export REBOB_BACKEND=postgres
rebob serve --transport http --port 8000
```
