/*
  # Fix Auth RLS Initialization Plan

  This migration optimizes RLS policies by wrapping auth.uid() calls in SELECT statements.
  This prevents the auth function from being re-evaluated for each row, significantly improving query performance.

  ## Changes
  
  1. **Drop Existing Policies** - Remove current policies on screener_presets
  2. **Recreate Optimized Policies** - Use (select auth.uid()) instead of auth.uid()

  ## Performance Impact
  
  - Auth function evaluated once per query instead of once per row
  - Significant performance improvement for queries with many rows
  - Follows Supabase best practices for RLS performance

  See: https://supabase.com/docs/guides/database/postgres/row-level-security#call-functions-with-select
*/

-- Drop existing policies
DROP POLICY IF EXISTS "Users can view presets" ON screener_presets;
DROP POLICY IF EXISTS "Users can create presets" ON screener_presets;
DROP POLICY IF EXISTS "Users can insert own presets" ON screener_presets;
DROP POLICY IF EXISTS "Users can update own presets" ON screener_presets;
DROP POLICY IF EXISTS "Users can delete own presets" ON screener_presets;

-- Recreate policies with optimized auth.uid() calls

-- SELECT: Users can view own presets and public presets
CREATE POLICY "Users can view presets"
  ON screener_presets
  FOR SELECT
  TO authenticated
  USING (
    (select auth.uid()) = user_id OR is_public = true
  );

-- INSERT: Users can create their own presets (single policy)
CREATE POLICY "Users can insert own presets"
  ON screener_presets
  FOR INSERT
  TO authenticated
  WITH CHECK (
    (select auth.uid()) = user_id
  );

-- UPDATE: Users can update their own presets
CREATE POLICY "Users can update own presets"
  ON screener_presets
  FOR UPDATE
  TO authenticated
  USING ((select auth.uid()) = user_id)
  WITH CHECK ((select auth.uid()) = user_id);

-- DELETE: Users can delete their own presets
CREATE POLICY "Users can delete own presets"
  ON screener_presets
  FOR DELETE
  TO authenticated
  USING ((select auth.uid()) = user_id);
