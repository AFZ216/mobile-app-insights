-- One row per month; each score column becomes a separate line in Metabase.
-- The window covers the current month and the previous 11 calendar months.
SELECT
    DATE_TRUNC('month', r.review_at)::date AS review_month,
    ROUND(AVG(r.score) FILTER (WHERE a.category = 'Dating & Chat')::numeric, 2) AS dating_chat_score,
    ROUND(AVG(r.score) FILTER (WHERE a.category = 'Messaging')::numeric, 2) AS messaging_score,
    ROUND(AVG(r.score) FILTER (WHERE a.category = 'Operator')::numeric, 2) AS operator_score,
    ROUND(AVG(r.score) FILTER (WHERE a.category = 'Social Media')::numeric, 2) AS social_media_score,
    ROUND(AVG(r.score) FILTER (WHERE a.category = 'Video Streaming')::numeric, 2) AS video_streaming_score,
    ROUND(AVG(r.score) FILTER (WHERE a.category = 'Word Game')::numeric, 2) AS word_game_score
FROM reviews AS r
JOIN applications AS a ON a.id = r.app_id
WHERE r.score BETWEEN 1 AND 5
  AND r.review_at >= DATE_TRUNC('month', CURRENT_DATE) - INTERVAL '11 months'
  AND r.review_at < DATE_TRUNC('month', CURRENT_DATE) + INTERVAL '1 month'
GROUP BY review_month
ORDER BY review_month;
