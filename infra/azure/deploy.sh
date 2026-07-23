#!/usr/bin/env bash
# Provisions an Azure Database for PostgreSQL Flexible Server for this project.
#
# You run this yourself (not an AI agent) -- it creates real, billable Azure
# resources under your subscription. Requires the Azure CLI (az) and `az login`
# to have been run already.
set -euo pipefail

# ---- Configuration -- edit these before running ----
RESOURCE_GROUP="retail-analytics-rg"
LOCATION="eastus"
PG_SERVER_NAME="retail-analytics-pg-$RANDOM"   # must be globally unique across Azure
PG_ADMIN_USER="pgadmin"
PG_DB_NAME="retail_analytics"
PG_SKU="Standard_B1ms"        # Burstable tier -- cheapest tier suitable for a demo
PG_STORAGE_GB=32
PG_VERSION=16
# -----------------------------------------------------

echo "This creates billable Azure resources under your subscription:"
echo "  - 1x PostgreSQL Flexible Server (Burstable $PG_SKU, ~\$12-25/month)"
echo "  - $PG_STORAGE_GB GB storage"
echo "See infra/azure/README.md for current pricing and teardown instructions."
read -p "Continue? (y/N) " CONFIRM
[[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]] || { echo "Aborted."; exit 1; }

read -s -p "Set an admin password for Postgres (12+ chars, mixed case/digits/symbols): " PG_ADMIN_PASSWORD
echo

echo "Creating resource group $RESOURCE_GROUP in $LOCATION..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION"

echo "Detecting your public IP (used to scope the server's firewall rule)..."
MY_IP=$(curl -s https://api.ipify.org)
echo "Your IP: $MY_IP"

echo "Creating PostgreSQL Flexible Server $PG_SERVER_NAME (this takes several minutes)..."
az postgres flexible-server create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$PG_SERVER_NAME" \
  --location "$LOCATION" \
  --admin-user "$PG_ADMIN_USER" \
  --admin-password "$PG_ADMIN_PASSWORD" \
  --sku-name "$PG_SKU" \
  --tier Burstable \
  --storage-size "$PG_STORAGE_GB" \
  --version "$PG_VERSION" \
  --public-access "$MY_IP-$MY_IP" \
  --yes

echo "Creating database $PG_DB_NAME..."
az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$PG_SERVER_NAME" \
  --database-name "$PG_DB_NAME"

cat <<EOF

Done. Connection details:
  Host:     $PG_SERVER_NAME.postgres.database.azure.com
  Database: $PG_DB_NAME
  User:     $PG_ADMIN_USER
  Port:     5432

Next steps (see infra/azure/README.md for the full walkthrough):
  1. Update .env with the values above (PGHOST, PGDATABASE, PGUSER, PGPASSWORD).
  2. Apply the schema against the new host:
       psql "host=$PG_SERVER_NAME.postgres.database.azure.com port=5432 dbname=$PG_DB_NAME user=$PG_ADMIN_USER sslmode=require" -v ON_ERROR_STOP=1 -f database/schema/01_dimensions.sql
       (repeat for 02_facts.sql, 03_indexes_partitions.sql, 04_analytics_schema.sql)
  3. Re-run the pipeline against the cloud DB:
       python -m etl.run_pipeline
       python -m analytics.forecasting.sales_forecast
       python -m analytics.segmentation.customer_segmentation
       python -m analytics.profitability.profitability_analysis
       python -m analytics.inventory.inventory_optimization
  4. Point Power BI at the new host and republish.

If your IP changes later (different network, VPN, etc.), add a new firewall rule:
  az postgres flexible-server firewall-rule create \\
    --resource-group "$RESOURCE_GROUP" --name "$PG_SERVER_NAME" \\
    --rule-name "AllowMyIP2" --start-ip-address <new-ip> --end-ip-address <new-ip>

To tear everything down and stop being billed:
  az group delete --name "$RESOURCE_GROUP" --yes --no-wait
EOF
