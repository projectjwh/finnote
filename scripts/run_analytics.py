"""Run analytics engine on collected market data and save results."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analytics import compute_all_analytics

data = json.loads(Path("outputs/market_data_latest.json").read_text())
analytics = compute_all_analytics(data)

# Serialize for JSON (dataclasses -> dicts)
export = {
    "anomalies_count": len(analytics.get("anomalies", [])),
    "divergences_count": len(analytics.get("divergences", [])),
    "breadth_score": analytics["breadth"].breadth_score,
    "vix_percentile": analytics.get("vix_percentile"),
    "hv_iv_ratio": analytics.get("hv_iv_ratio"),
}
Path("outputs/analytics_latest.json").write_text(json.dumps(export, indent=2, default=str))

print(f"Analytics: {export['anomalies_count']} anomalies, "
      f"{export['divergences_count']} divergences, "
      f"breadth {export['breadth_score']:.0f}/100")
