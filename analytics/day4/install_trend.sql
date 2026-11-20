-- One latest store snapshot per app and hour keeps the time series readable.
-- Installs are reported totals, not new installs during the hour.
WITH hourly_snapshots AS (
    SELECT
        m.*,
        DATE_TRUNC('hour', m.scraped_at) AS snapshot_hour,
        ROW_NUMBER() OVER (
            PARTITION BY m.app_id, DATE_TRUNC('hour', m.scraped_at)
            ORDER BY m.scraped_at DESC, m.id DESC
        ) AS row_number
    FROM app_metrics AS m
    WHERE m.real_installs IS NOT NULL
)
SELECT
    s.snapshot_hour,
    a.title AS app_title,
    a.category,
    s.real_installs,
    s.min_installs,
    s.scraped_at AS observed_at
FROM hourly_snapshots AS s
JOIN applications AS a ON a.id = s.app_id
WHERE s.row_number = 1
ORDER BY s.snapshot_hour, a.title;
