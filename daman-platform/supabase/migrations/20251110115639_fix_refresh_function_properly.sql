/*
  # Fix Refresh Materialized View Function

  This migration properly fixes the refresh_materialized_view function by:
  1. Dropping all existing versions
  2. Recreating with SECURITY INVOKER and fixed search_path

  ## Changes
  
  1. **Drop Existing Functions** - Remove all versions with different signatures
  2. **Recreate with Proper Security** - SECURITY INVOKER and search_path = public

  ## Security Notes
  
  - Fixed search_path prevents schema manipulation
  - SECURITY INVOKER uses caller's privileges
  - More secure than SECURITY DEFINER
*/

-- Drop all versions of the function
DROP FUNCTION IF EXISTS refresh_materialized_view() CASCADE;
DROP FUNCTION IF EXISTS refresh_materialized_view(text) CASCADE;

-- Recreate with proper security settings
CREATE OR REPLACE FUNCTION refresh_materialized_view()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
  -- Refresh the materialized view when underlying data changes
  -- Note: CONCURRENTLY option requires a unique index
  REFRESH MATERIALIZED VIEW CONCURRENTLY stock_screener_data;
  RETURN NULL;
EXCEPTION
  WHEN OTHERS THEN
    -- If concurrent refresh fails, try regular refresh
    REFRESH MATERIALIZED VIEW stock_screener_data;
    RETURN NULL;
END;
$$;

-- Add comment documenting the security settings
COMMENT ON FUNCTION refresh_materialized_view() IS 
'Refreshes stock_screener_data materialized view. Uses SECURITY INVOKER and fixed search_path for security.';
