/*
  # Add function to refresh materialized view

  1. **New Function**
    - `refresh_materialized_view` - Refreshes stock_screener_data materialized view
  
  2. **Purpose**
    - Allow concurrent refresh of materialized views
    - Update screener data after new stock data is inserted
*/

-- Create function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_materialized_view(view_name text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  EXECUTE format('REFRESH MATERIALIZED VIEW CONCURRENTLY %I', view_name);
EXCEPTION
  WHEN OTHERS THEN
    EXECUTE format('REFRESH MATERIALIZED VIEW %I', view_name);
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION refresh_materialized_view(text) TO authenticated, anon;
