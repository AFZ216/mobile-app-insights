-- Review scores describe only the reviews collected for this project.
-- The date columns show the coverage of each category; they are not store scores.
SELECT
    a.category,
    COUNT(r.review_id) AS review_count,
    ROUND(AVG(r.score)::numeric, 2) AS average_review_score,
    MIN(r.review_at)::date AS first_review_date,
    MAX(r.review_at)::date AS last_review_date
FROM applications AS a
JOIN reviews AS r ON r.app_id = a.id
WHERE r.score BETWEEN 1 AND 5
  AND r.review_at IS NOT NULL
GROUP BY a.category
ORDER BY a.category;
