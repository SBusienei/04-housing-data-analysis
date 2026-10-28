-- Question: What is the final-test risk distribution for the primary model?
-- src.export_dashboard prepares this session's temporary prediction table.
-- Bands are illustrative display boundaries, not business intervention rules.
WITH bands(sort_order, risk_band, lower_bound, upper_bound) AS (
    VALUES (1, 'Low: [0, 0.3)', 0.0, 0.3),
           (2, 'Medium: [0.3, 0.7)', 0.3, 0.7),
           (3, 'High: [0.7, 1]', 0.7, 1.0)
)
SELECT b.risk_band, b.lower_bound, b.upper_bound,
       count(p.source_record_number) AS bookings,
       avg(p.risk) AS mean_predicted_risk,
       avg(p.actual::numeric) AS observed_cancellation_rate,
       'final_test_later_arrivals' AS population,
       'logistic_regression' AS model
FROM bands AS b
LEFT JOIN pg_temp.model_test_predictions AS p
    ON p.risk >= b.lower_bound
   AND (p.risk < b.upper_bound OR (b.upper_bound = 1.0 AND p.risk <= 1.0))
GROUP BY b.sort_order, b.risk_band, b.lower_bound, b.upper_bound
ORDER BY b.sort_order;

