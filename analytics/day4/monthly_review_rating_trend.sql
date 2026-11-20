-- Monthly averages use only the reviews collected for this project.
-- Review counts help identify months with too little data for a useful comparison.
SELECT
    DATE_TRUNC('month', r.review_at)::date AS review_month,
    a.title AS app_title,
    a.category,
    COUNT(*) AS review_count,
    ROUND(AVG(r.score)::numeric, 2) AS average_review_score
FROM reviews AS r
JOIN applications AS a ON a.id = r.app_id
WHERE r.review_at IS NOT NULL
  AND r.score BETWEEN 1 AND 5
GROUP BY review_month, a.id, a.title, a.category
ORDER BY review_month, a.title;
