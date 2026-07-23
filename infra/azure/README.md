# Azure Deployment

Deploys the warehouse to **Azure Database for PostgreSQL Flexible Server**.
Everything here creates real, billable resources under your own Azure
subscription -- these commands are meant for you to run yourself (an AI
assistant has no Azure credentials and won't run them for you).

## 1. Install the Azure CLI

```bash
winget install -e --id Microsoft.AzureCLI
```
(or download from https://learn.microsoft.com/cli/azure/install-azure-cli-windows).
Restart your terminal afterward, then confirm:
```bash
az version
```

## 2. Log in

```bash
az login
```
This opens a browser to authenticate. If you have more than one subscription,
set the one you want to use:
```bash
az account set --subscription "<subscription name or id>"
```

## 3. Run the deployment script

```bash
bash infra/azure/deploy.sh
```
This creates:
- A resource group (`retail-analytics-rg` by default)
- A PostgreSQL Flexible Server, **Burstable B1ms** tier (1 vCore, 2 GiB RAM), 32 GB storage
- A firewall rule scoped to your current public IP only
- The `retail_analytics` database on that server

It prompts for confirmation and for an admin password before creating anything.

**Estimated cost**: Burstable B1ms is roughly **$12-25/month** (varies by region;
check https://azure.microsoft.com/pricing/details/postgresql/flexible-server/
for current pricing). Storage and outbound bandwidth are billed separately but
minor at this scale for demo/portfolio use. Delete the resource group when you're
done showing the project (step 6) to stop being billed.

## 4. Load the schema and data into the cloud database

```bash
# Update .env with the new host/credentials the script printed, then:
PGPASSWORD=<your-password> psql "host=<server>.postgres.database.azure.com port=5432 dbname=retail_analytics user=pgadmin sslmode=require" \
  -v ON_ERROR_STOP=1 -f database/schema/01_dimensions.sql

# repeat for 02_facts.sql, 03_indexes_partitions.sql, 04_analytics_schema.sql

python -m etl.run_pipeline
python -m analytics.forecasting.sales_forecast
python -m analytics.segmentation.customer_segmentation
python -m analytics.profitability.profitability_analysis
python -m analytics.inventory.inventory_optimization
```
Loading ~9M rows over the internet to a Burstable-tier server will be noticeably
slower than the local run (expect it to take longer than the ~22 minutes seen
locally) -- that's expected given the smaller compute tier and network latency.

## 5. Point Power BI at the cloud database

In Power BI Desktop: **Home -> Transform Data -> Data source settings**, change
the Postgres connection from `localhost` to `<server>.postgres.database.azure.com`,
update credentials, refresh. Once you publish the report to the Power BI service,
you can set up a scheduled refresh directly against the Azure database (Power BI
service needs a data gateway only for on-prem sources -- an Azure-hosted Postgres
doesn't need one).

## 6. Tear down when you're done

```bash
az group delete --name retail-analytics-rg --yes --no-wait
```
This deletes the server, the database, and all firewall rules in one command.
There's no separate step needed -- deleting the resource group removes everything
created above.
