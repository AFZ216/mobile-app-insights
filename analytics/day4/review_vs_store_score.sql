-- Compare the collected review sample with the latest available store snapshot.
-- A missing store score stays NULL; it must not be treated as zero.
WITH latest_store_score AS (
    SELECT DISTINCT ON (app_id)
        app_id,
        score AS store_score,
        ratings AS store_rating_count,
        scraped_at AS store_scraped_at
    FROM app_metrics
    ORDER BY app_id, scraped_at DESC, id DESC
),
collected_reviews AS (
    SELECT
        app_id,
        COUNT(*) AS collected_review_count,
        ROUND(AVG(score)::numeric, 2) AS average_review_score,
        MIN(review_at)::date AS first_review_date,
        MAX(review_at)::date AS last_review_date
    FROM reviews
    WHERE score BETWEEN 1 AND 5
      AND review_at IS NOT NULL
    GROUP BY app_id
)
SELECT
    a.category,
    a.title AS app_title,
    r.collected_review_count,
    r.average_review_score,
    r.first_review_date,
    r.last_review_date,
    s.store_score,
    s.store_rating_count,
    s.store_scraped_at
FROM applications AS a
LEFT JOIN collected_reviews AS r ON r.app_id = a.id
LEFT JOIN latest_store_score AS s ON s.app_id = a.id
WHERE a.is_active
ORDER BY a.category, a.title;
