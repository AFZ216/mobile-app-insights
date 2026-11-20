-- Show the sample size behind each monthly category score in the trend chart.
-- A month with only a few collected reviews can have an unstable average.
SELECT
    DATE_TRUNC('month', r.review_at)::date AS review_month,
    a.category,
    COUNT(*) AS review_count
FROM reviews AS r
JOIN applications AS a ON a.id = r.app_id
WHERE r.score BETWEEN 1 AND 5
  AND r.review_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months'
  AND r.review_at < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
GROUP BY review_month, a.category
ORDER BY review_month DESC, a.category;
