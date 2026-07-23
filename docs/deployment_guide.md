# Deployment Guide

Two deployment targets: **local** (for development and the initial dashboard
build) and **Azure** (for a live, shareable deployment).

## Local setup

1. Install PostgreSQL 16+ and Python 3.11+.
2. Create the database and apply the schema -- see
   [etl_runbook.md](etl_runbook.md) steps 1-2.
3. `pip install -r requirements.txt`, copy `.env.example` to `.env`, fill in
   your local Postgres credentials.
4. Run the ETL pipeline and analytics modules -- [etl_runbook.md](etl_runbook.md)
   steps 2-3.
5. Build the Power BI report against `localhost` -- see
   [powerbi/build_guide.md](../powerbi/build_guide.md).

This is the recommended path for all development, testing changes to the
generator or analytics modules, and the initial dashboard build -- it's free,
fast to iterate on, and has no network latency.

## Azure deployment

Once the local setup works end-to-end, the same schema and pipeline can target
an **Azure Database for PostgreSQL Flexible Server** instead of `localhost`.
Full walkthrough, cost estimate, and teardown instructions:
[infra/azure/README.md](../infra/azure/README.md).

Summary of the flow:
1. `az login`, then `bash infra/azure/deploy.sh` -- provisions the server
   (Burstable B1ms, ~$12-25/month) and a `retail_analytics` database.
2. Update `.env` to point at the new host; re-apply the schema and re-run the
   pipeline + analytics modules against it (same commands, different host).
3. Repoint Power BI's data source from `localhost` to the Azure host; if
   published to the Power BI service, set up a scheduled refresh directly
   against Azure (no gateway needed for a cloud-hosted database).
4. `az group delete --name retail-analytics-rg --yes --no-wait` when you're
   done demoing it, to stop being billed.

## What's *not* automated, and why

- **Provisioning Azure resources**: requires your credentials and creates
  billable infrastructure -- you run `deploy.sh` yourself, not an AI agent.
- **Building the Power BI report**: Power BI Desktop is a GUI application with
  no scripting surface for report authoring; the `.pbix` is hand-built using
  the prepared data model and DAX measures as a guide.
- **CI/CD**: intentionally out of scope for a project of this size. A single
  developer running the pipeline on demand, both locally and against Azure, is
  the appropriate level of operational complexity here -- adding a pipeline
  orchestrator or CI system wouldn't reflect anything this project actually
  needs.
