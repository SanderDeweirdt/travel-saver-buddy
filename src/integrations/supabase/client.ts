
import { createClient } from '@supabase/supabase-js';
import type { Database } from './types';

const SUPABASE_URL = "https://syzbxllcmgvyhjzuzead.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InN5emJ4bGxjbWd2eWhqenV6ZWFkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDExNTk5NzksImV4cCI6MjA1NjczNTk3OX0.rPH60Mle69zXhYRvhokps02srM39gghnCTGO96_B0e4";

export const supabase = createClient<Database>(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);
