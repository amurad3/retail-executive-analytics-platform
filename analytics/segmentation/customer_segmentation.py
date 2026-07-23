"""
Customer segmentation via RFM analysis (Recency/Frequency/Monetary) plus a
KMeans clustering pass over the same features -- the dashboard gets both the
classic business-rule segment (transparent, easy to explain to executives)
and a data-driven cluster segment.
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from etl.db import get_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s %(message)s")
logger = logging.getLogger("customer_segmentation")

N_CLUSTERS = 4
CLUSTER_NAMES_BY_MONETARY_RANK = ["Champions", "Loyal Customers", "At Risk", "Lost / Dormant"]

RFM_BASE_QUERY = """
    SELECT
        c.customer_id,
        (SELECT max(d2.full_date) FROM fact_sales f2 JOIN dim_date d2 ON d2.date_id = f2.date_id)
            - MAX(d.full_date) AS recency_days,
        COUNT(*) FILTER (WHERE NOT f.is_return) AS frequency,
        COALESCE(SUM(f.net_revenue) FILTER (WHERE NOT f.is_return), 0) AS monetary
    FROM dim_customer c
    JOIN fact_sales f ON f.customer_id = c.customer_id
    JOIN dim_date d ON d.date_id = f.date_id
    GROUP BY c.customer_id
"""


def load_rfm_base(engine) -> pd.DataFrame:
    df = pd.read_sql(RFM_BASE_QUERY, engine)
    df["recency_days"] = df["recency_days"].astype(int)
    return df


def _rank_qcut_score(series: pd.Series, ascending_labels: bool) -> pd.Series:
    """qcut on the rank (not the raw value) so duplicate values never collapse bins."""
    labels = [1, 2, 3, 4, 5] if ascending_labels else [5, 4, 3, 2, 1]
    return pd.qcut(series.rank(method="first"), 5, labels=labels).astype(int)


def rfm_scores(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["r_score"] = _rank_qcut_score(df["recency_days"], ascending_labels=False)
    df["f_score"] = _rank_qcut_score(df["frequency"], ascending_labels=True)
    df["m_score"] = _rank_qcut_score(df["monetary"], ascending_labels=True)
    df["rfm_score"] = df["r_score"] + df["f_score"] + df["m_score"]

    def segment(score):
        if score >= 13:
            return "Champions"
        if score >= 10:
            return "Loyal Customers"
        if score >= 7:
            return "Potential Loyalist"
        if score >= 4:
            return "At Risk"
        return "Lost"

    df["rfm_segment"] = df["rfm_score"].apply(segment)
    return df


def cluster_customers(df: pd.DataFrame) -> pd.DataFrame:
    features = df[["recency_days", "frequency", "monetary"]].copy()
    features["frequency"] = np.log1p(features["frequency"])
    features["monetary"] = np.log1p(features["monetary"].clip(lower=0))

    scaled = StandardScaler().fit_transform(features)
    kmeans = KMeans(n_clusters=N_CLUSTERS, random_state=42, n_init=10).fit(scaled)

    df = df.copy()
    df["cluster_id"] = kmeans.labels_

    cluster_monetary_rank = (
        df.groupby("cluster_id")["monetary"].mean().sort_values(ascending=False).index.tolist()
    )
    name_by_cluster = {cid: CLUSTER_NAMES_BY_MONETARY_RANK[rank]
                        for rank, cid in enumerate(cluster_monetary_rank)}
    df["cluster_segment"] = df["cluster_id"].map(name_by_cluster)
    return df


def run(engine=None) -> None:
    engine = engine or get_engine()
    base = load_rfm_base(engine)
    logger.info("Base RFM population: %d customers with at least one purchase", len(base))

    scored = rfm_scores(base)
    result = cluster_customers(scored)

    logger.info("RFM segment distribution:\n%s", result["rfm_segment"].value_counts())
    logger.info("Cluster segment distribution:\n%s", result["cluster_segment"].value_counts())

    result.to_sql("customer_segments", engine, schema="analytics", if_exists="replace", index=False)
    logger.info("Wrote %d rows to analytics.customer_segments", len(result))


if __name__ == "__main__":
    run()
