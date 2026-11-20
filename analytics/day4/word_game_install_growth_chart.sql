-- Percentage change in total installs since each app's first observed snapshot.
-- The three apps share a category; percentages make their different install scales comparable.
-- This is observed growth over the crawler window, not new installs per hour.
WITH hourly_snapshots AS (
    SELECT
        DATE_TRUNC('hour', m.scraped_at) AS snapshot_hour,
        a.title AS app_title,
        m.real_installs,
        ROW_NUMBER() OVER (
            PARTITION BY m.app_id, DATE_TRUNC('hour', m.scraped_at)
            ORDER BY m.scraped_at DESC, m.id DESC
        ) AS snapshot_rank
    FROM app_metrics AS m
    JOIN applications AS a ON a.id = m.app_id
    WHERE a.title IN ('Amirza', 'Fandogh', 'Samavar')
      AND m.real_installs > 0
),
with_baseline AS (
    SELECT
        snapshot_hour,
        app_title,
        real_installs,
        FIRST_VALUE(real_installs) OVER (
            PARTITION BY app_title ORDER BY snapshot_hour
        ) AS first_installs
    FROM hourly_snapshots
    WHERE snapshot_rank = 1
),
growth AS (
    SELECT
        snapshot_hour,
        app_title,
        ROUND(100.0 * (real_installs - first_installs) / first_installs, 4) AS growth_percent
    FROM with_baseline
)
SELECT
    snapshot_hour,
    MAX(growth_percent) FILTER (WHERE app_title = 'Amirza') AS amirza_growth_percent,
    MAX(growth_percent) FILTER (WHERE app_title = 'Fandogh') AS fandogh_growth_percent,
    MAX(growth_percent) FILTER (WHERE app_title = 'Samavar') AS samavar_growth_percent
FROM growth
GROUP BY snapshot_hour
ORDER BY snapshot_hour;
