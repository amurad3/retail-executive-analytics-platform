-- ============================================================
-- Retail Executive Analytics Platform
-- Analytics schema -- destination for derived tables written by the
-- forecasting, segmentation, profitability, and inventory modules.
-- Power BI reads exclusively from here plus the star schema above.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS analytics;
