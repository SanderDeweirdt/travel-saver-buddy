
import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

// Constants and configuration
const FETCH_PRICES_FUNCTION_URL = "https://syzbxllcmgvyhjzuzead.supabase.co/functions/v1/fetch-hotel-prices";
const SUPABASE_ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") as string;

// CORS headers for browser requests
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// Setup the header for the function call
const functionHeaders = {
  "Content-Type": "application/json",
  "Authorization": `Bearer ${SUPABASE_ANON_KEY}`,
  "x-scheduled-function": "true"
};

serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    console.log("Scheduler triggered, calling fetch-hotel-prices function");
    
    // Call the fetch-hotel-prices function
    const response = await fetch(FETCH_PRICES_FUNCTION_URL, {
      method: "POST",
      headers: functionHeaders,
      body: JSON.stringify({ processAll: true })
    });
    
    if (!response.ok) {
      throw new Error(`Failed to call fetch-hotel-prices: ${response.status} ${response.statusText}`);
    }
    
    const result = await response.json();
    console.log("Fetch hotel prices result:", result);
    
    return new Response(JSON.stringify({
      success: true,
      message: "Scheduler executed successfully",
      result
    }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    });
  } catch (error) {
    console.error("Error in scheduler function:", error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" }
    });
  }
});
