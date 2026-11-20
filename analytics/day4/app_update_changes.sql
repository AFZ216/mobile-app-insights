-- Show changes between store snapshots, not every repeated crawl result.
-- observed_at is when our crawler noticed a change; store_updated_at comes from Google Play.
WITH ordered_snapshots AS (
    SELECT
        m.*,
        ROW_NUMBER() OVER (PARTITION BY m.app_id ORDER BY m.scraped_at, m.id) AS snapshot_number,
        LAG(m.version) OVER (PARTITION BY m.app_id ORDER BY m.scraped_at, m.id) AS previous_version,
        LAG(m.store_updated_at) OVER (PARTITION BY m.app_id ORDER BY m.scraped_at, m.id) AS previous_store_updated_at
    FROM app_metrics AS m
)
SELECT
    a.title AS app_title,
    a.category,
    s.scraped_at AS observed_at,
    s.previous_version,
    s.version AS current_version,
    s.previous_store_updated_at,
    s.store_updated_at,
    s.real_installs
FROM ordered_snapshots AS s
JOIN applications AS a ON a.id = s.app_id
WHERE s.snapshot_number > 1
  AND (
      s.version IS DISTINCT FROM s.previous_version
      OR s.store_updated_at IS DISTINCT FROM s.previous_store_updated_at
  )
ORDER BY s.scraped_at, a.title;
