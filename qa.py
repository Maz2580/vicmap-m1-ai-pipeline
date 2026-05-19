import logging
from pathlib import Path
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import geopandas as gpd
    from shapely.geometry import Point
except Exception:
    gpd = None

from config import EXTRACT_DIR, RATES_DB_CSV, QA_REPORT, OPENAI_API_KEY


def perform_qa(parcels_path: Path = None, rates_path: Path = None, report_path: Path = None) -> pd.DataFrame:
    parcels_path = parcels_path or (EXTRACT_DIR / "m1_parcels.shp")
    rates_path = rates_path or RATES_DB_CSV
    report_path = report_path or QA_REPORT

    if gpd is None:
        raise RuntimeError("geopandas is not available. Install geopandas to run QA checks.")

    logger.info("Loading parcels from %s", parcels_path)
    parcels = gpd.read_file(parcels_path)

    logger.info("Loading rates DB from %s", rates_path)
    # rates could be a CSV with lat/lon columns, or a spatial file
    try:
        rates = gpd.read_file(rates_path)
    except Exception:
        rates_df = pd.read_csv(rates_path)
        if "latitude" in rates_df.columns and "longitude" in rates_df.columns:
            rates = gpd.GeoDataFrame(
                rates_df,
                geometry=gpd.points_from_xy(rates_df.longitude, rates_df.latitude),
                crs=parcels.crs,
            )
        else:
            raise

    # Spatial join: ensure each rateable property matches a parcel
    joined = gpd.sjoin(rates, parcels, how="left", predicate="within")
    anomalies = joined[joined.index_right.isna()].copy()
    anomalies["issue"] = "Unmatched parcel"

    # Flag splits: two or more child parcels for one parent identifier
    if "parent_id" in joined.columns:
        counts = joined.groupby("parent_id").size().reset_index(name="child_count")
        splits = counts[counts.child_count > 1].copy()
        splits["issue"] = "Possible split"
    else:
        splits = pd.DataFrame(columns=["parent_id", "child_count", "issue"])  # empty

    qa_df = pd.concat([anomalies.drop(columns="geometry", errors="ignore"), splits], ignore_index=True, sort=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    qa_df.to_csv(report_path, index=False)
    logger.info("QA check complete: %s issues written to %s", len(qa_df), report_path)
    return qa_df


def ai_validate_splits(splits_df: pd.DataFrame) -> pd.DataFrame:
    """Optional: call OpenAI to review ambiguous splits. Requires OPENAI_API_KEY env var."""
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")

    try:
        import openai
    except Exception:
        raise RuntimeError("openai package not installed")

    openai.api_key = OPENAI_API_KEY

    def ask(row):
        prompt = f"Parent ID: {row.get('parent_id')} has {row.get('child_count')} children. Is this likely a valid split or an error?"
        resp = openai.ChatCompletion.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
        return resp.choices[0].message.content.strip()

    splits_df = splits_df.copy()
    splits_df["ai_opinion"] = splits_df.apply(ask, axis=1)
    return splits_df
