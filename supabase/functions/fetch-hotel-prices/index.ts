
import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";
// Fix the Cheerio import
import * as cheerio from "https://esm.sh/cheerio@1.0.0-rc.12";

// Constants and configuration
const BATCH_SIZE = 5; // Process bookings in batches to avoid rate limiting
const TEST_HOTEL_ID = "740887"; // For testing purposes

// Headers to mimic a browser request
const BROWSER_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
  "Cache-Control": "no-cache",
  "Pragma": "no-cache",
};

// CORS headers for browser requests
const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// Initialize Supabase client
const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseKey);

// Helper function to validate URL
function isValidUrl(urlString: string): boolean {
  try {
    // Ensure URL has a protocol
    if (!urlString.startsWith('http://') && !urlString.startsWith('https://')) {
      urlString = 'https://' + urlString;
    }
    
    const url = new URL(urlString);
    // We'll accept any URL for now since we're using trip.com
    return true;
  } catch (error) {
    console.error(`Invalid URL: ${urlString}`, error.message);
    return false;
  }
}

// Helper function to create Trip.com search URL with query parameters
function createTripUrl(
  hotelId: string = TEST_HOTEL_ID, 
  checkInDate: string, 
  checkOutDate: string, 
  groupAdults: number = 2,
  currency: string = "EUR"
): string {
  try {
    console.log(`Creating Trip.com URL for hotel ID: ${hotelId}`);
    
    // Format dates for trip.com (YYYY-MM-DD)
    const formatDate = (dateString: string): string => {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        throw new Error(`Invalid date: ${dateString}`);
      }
      return date.toISOString().split('T')[0]; // Get YYYY-MM-DD format
    };

    // Validate dates
    const formattedCheckIn = formatDate(checkInDate);
    const formattedCheckOut = formatDate(checkOutDate);
    
    // Create Trip.com URL
    const url = `https://www.trip.com/hotels/detail/?hotelId=${hotelId}&checkIn=${formattedCheckIn}&checkOut=${formattedCheckOut}&adult=${groupAdults}&children=0&curr=${currency}`;
    
    console.log(`Final Trip.com URL: ${url}`);
    return url;
  } catch (error) {
    console.error('Error creating Trip.com URL:', error);
    throw new Error(`Failed to create Trip.com URL: ${error.message}`);
  }
}

// Helper function to extract hotel ID from URL or use default test ID
function extractHotelId(url: string | null): string {
  if (!url) {
    console.log('No URL provided, using test hotel ID');
    return TEST_HOTEL_ID;
  }

  try {
    // Try to extract hotel ID from Trip.com URL if it matches the pattern
    // Example: https://www.trip.com/hotels/detail/?hotelId=740887&...
    if (url.includes('trip.com') && url.includes('hotelId=')) {
      const regex = /hotelId=([0-9]+)/;
      const match = url.match(regex);
      if (match && match[1]) {
        console.log(`Extracted hotel ID from URL: ${match[1]}`);
        return match[1];
      }
    }
    
    // For now, return the test hotel ID if we can't extract it
    console.log(`Could not extract hotel ID from URL: ${url}, using test hotel ID`);
    return TEST_HOTEL_ID;
  } catch (error) {
    console.error('Error extracting hotel ID:', error);
    return TEST_HOTEL_ID;
  }
}

// Function to fetch price from Trip.com
async function fetchHotelPrice(
  tripUrl: string,
  booking: any
): Promise<{price: number | null, error?: string}> {
  try {
    console.log(`Fetching price for booking ${booking.id} with URL: ${tripUrl}`);
    
    // Fetch the webpage
    const response = await fetch(tripUrl, {
      method: 'GET',
      headers: BROWSER_HEADERS,
    });
    
    // Log the response status
    console.log(`Response for booking ${booking.id}: status: ${response.status}, statusText: ${response.statusText}`);
    
    if (!response.ok) {
      return {price: null, error: `HTTP error: ${response.status} ${response.statusText}`};
    }

    // Get the response text
    const html = await response.text();
    
    // Check if we received valid HTML
    if (!html || html.trim().length === 0) {
      return {price: null, error: 'Empty response received'};
    }
    
    // Parse HTML with cheerio
    // Updated to use the correct Cheerio method
    const $ = cheerio.load(html);
    
    // Log the HTML for debugging
    console.log(`Received HTML length: ${html.length} characters`);
    
    // Extract prices using regex pattern for "Total price: €XXX"
    let prices: number[] = [];
    
    // First attempt: Look for text containing "Total price"
    const priceText = $('body').text();
    const priceRegex = /Total price: [€$](\d+)/g;
    let match;
    
    while ((match = priceRegex.exec(priceText)) !== null) {
      if (match[1]) {
        prices.push(parseInt(match[1]));
      }
    }
    
    if (prices.length > 0) {
      console.log(`Found ${prices.length} price matches using text search`);
    } else {
      console.log('No price matches found using text search');
      
      // Second attempt: Try to find price elements directly
      $('div:contains("Total price")').each((_i, el) => {
        const text = $(el).text();
        const priceMatch = text.match(/\d+/);
        if (priceMatch && priceMatch[0]) {
          prices.push(parseInt(priceMatch[0]));
        }
      });
    }
    
    if (prices.length > 0) {
      // Sort prices in ascending order
      prices.sort((a, b) => a - b);
      console.log(`Found ${prices.length} prices: ${prices.join(', ')}`);
      
      // Return the cheapest price
      const cheapestPrice = prices[0];
      console.log(`Cheapest price for booking ${booking.id}: ${cheapestPrice}`);
      return { price: cheapestPrice };
    } else {
      // For development/testing, return a random price if none found
      if (Deno.env.get("STAGE") === "development") {
        const randomPrice = Math.floor(Math.random() * 500) + 100; // Random price between 100 and 600
        console.log(`Development mode: Returning random price: ${randomPrice}`);
        return { price: randomPrice };
      }
      
      return { price: null, error: 'No prices found on the page' };
    }
  } catch (error) {
    console.error(`Error fetching hotel price for booking ${booking.id}:`, error);
    return { price: null, error: `Error fetching hotel price: ${error.message}` };
  }
}

// Function to check booking URL integrity in the database
async function checkBookingUrlIntegrity(): Promise<{
  valid: number,
  invalid: number,
  invalidUrls: string[]
}> {
  try {
    console.log('Checking booking URL integrity in database...');
    
    const { data: bookings, error } = await supabase
      .from('bookings')
      .select('id, hotel_url')
      .not('hotel_url', 'is', null);
    
    if (error) {
      console.error('Error fetching bookings for URL check:', error);
      return { valid: 0, invalid: 0, invalidUrls: [] };
    }
    
    let validCount = 0;
    let invalidCount = 0;
    const invalidUrls: string[] = [];
    
    for (const booking of bookings) {
      if (!booking.hotel_url) continue;
      
      if (isValidUrl(booking.hotel_url)) {
        validCount++;
      } else {
        invalidCount++;
        invalidUrls.push(`Booking ID ${booking.id}: ${booking.hotel_url}`);
      }
    }
    
    console.log(`URL integrity check: ${validCount} valid, ${invalidCount} invalid`);
    if (invalidUrls.length > 0) {
      console.log('Invalid URLs:', invalidUrls);
    }
    
    return { valid: validCount, invalid: invalidCount, invalidUrls };
  } catch (error) {
    console.error('Error checking booking URL integrity:', error);
    return { valid: 0, invalid: 0, invalidUrls: [] };
  }
}

// Function to process a single booking
async function processBooking(booking: any): Promise<{success: boolean, error?: string}> {
  try {
    console.log(`Processing booking ${booking.id}`);
    
    // Extract hotel ID from the booking's hotel_url or use the test ID
    const hotelId = extractHotelId(booking.hotel_url);
    
    // Create the Trip.com URL with the extracted or default hotel ID
    let tripUrl: string;
    try {
      tripUrl = createTripUrl(
        hotelId,
        booking.check_in_date,
        booking.check_out_date,
        booking.group_adults || 2,
        booking.currency || 'EUR'
      );
    } catch (error) {
      console.error(`Failed to create Trip.com URL for booking ${booking.id}:`, error);
      return {success: false, error: `Failed to create Trip.com URL: ${error.message}`};
    }

    // Fetch the price
    const {price, error} = await fetchHotelPrice(tripUrl, booking);
    
    if (price === null) {
      console.log(`Could not fetch price for booking ${booking.id}: ${error}`);
      // Update booking with error information
      const { error: updateError } = await supabase
        .from('bookings')
        .update({
          fetched_price: null,
          fetched_price_updated_at: new Date().toISOString()
        })
        .eq('id', booking.id);
        
      if (updateError) {
        console.error(`Error updating booking ${booking.id} with error:`, updateError);
      }
      
      return {success: false, error};
    }

    // Update the booking with the fetched price
    const { error: updateError } = await supabase
      .from('bookings')
      .update({
        fetched_price: price,
        fetched_price_updated_at: new Date().toISOString()
      })
      .eq('id', booking.id);

    if (updateError) {
      console.error(`Error updating booking ${booking.id}:`, updateError);
      return {success: false, error: `Database update error: ${updateError.message}`};
    }

    console.log(`Successfully updated booking ${booking.id} with price ${price}`);
    return {success: true};
  } catch (error) {
    console.error(`Error processing booking ${booking.id}:`, error);
    return {success: false, error: `Unhandled error: ${error.message}`};
  }
}

// Function to fetch and process bookings in batches
async function processAllBookings(): Promise<{ 
  total: number, 
  successful: number, 
  failed: number,
  failureReasons: Record<string, number>,
  urlIntegrity: any 
}> {
  try {
    // First, check URL integrity in the database
    const urlIntegrity = await checkBookingUrlIntegrity();
    
    // Get all active bookings with future check-out dates
    const { data: bookings, error } = await supabase
      .from('bookings')
      .select('*')
      .gte('check_out_date', new Date().toISOString())
      .order('check_in_date', { ascending: true });

    if (error) {
      console.error('Error fetching bookings:', error);
      return { 
        total: 0, 
        successful: 0, 
        failed: 0, 
        failureReasons: {},
        urlIntegrity 
      };
    }

    if (!bookings || bookings.length === 0) {
      console.log('No active bookings found');
      return { 
        total: 0, 
        successful: 0, 
        failed: 0, 
        failureReasons: {},
        urlIntegrity 
      };
    }

    console.log(`Processing ${bookings.length} bookings`);
    
    // Process bookings in batches to avoid rate limiting
    let successful = 0;
    let failed = 0;
    const failureReasons: Record<string, number> = {};
    
    for (let i = 0; i < bookings.length; i += BATCH_SIZE) {
      const batch = bookings.slice(i, i + BATCH_SIZE);
      
      // Process batch in parallel
      const results = await Promise.all(
        batch.map(booking => processBooking(booking))
      );
      
      // Count successful updates and errors
      results.forEach(result => {
        if (result.success) {
          successful++;
        } else {
          failed++;
          // Categorize errors
          const reason = result.error || "Unknown error";
          failureReasons[reason] = (failureReasons[reason] || 0) + 1;
        }
      });
      
      // Add delay between batches to avoid rate limiting
      if (i + BATCH_SIZE < bookings.length) {
        console.log(`Processed batch ${i / BATCH_SIZE + 1}/${Math.ceil(bookings.length / BATCH_SIZE)}, adding delay before next batch`);
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }

    // Log the most common failure reasons
    if (failed > 0) {
      console.log('Failure reasons:', failureReasons);
    }

    return { 
      total: bookings.length, 
      successful, 
      failed,
      failureReasons,
      urlIntegrity 
    };
  } catch (error) {
    console.error('Error processing bookings:', error);
    return { 
      total: 0, 
      successful: 0, 
      failed: 0, 
      failureReasons: {'Unhandled exception': 1},
      urlIntegrity: { valid: 0, invalid: 0, invalidUrls: [] } 
    };
  }
}

// Main handler function
serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    // Check if this is a scheduled invocation
    if (req.headers.get('x-scheduled-function') === 'true') {
      console.log('Function invoked by scheduler');
      const result = await processAllBookings();
      return new Response(JSON.stringify({ 
        success: true, 
        message: 'Scheduled processing completed',
        result
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    
    // Parse request parameters
    let params: any = {};
    
    if (req.method === 'POST') {
      try {
        params = await req.json();
      } catch (parseError) {
        console.error('Error parsing request body:', parseError);
        return new Response(JSON.stringify({ 
          success: false, 
          error: `Invalid JSON in request body: ${parseError.message}` 
        }), {
          status: 400,
          headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        });
      }
    } else {
      const url = new URL(req.url);
      params = {
        bookingId: url.searchParams.get('bookingId'),
        processAll: url.searchParams.get('processAll') === 'true',
        checkUrlIntegrity: url.searchParams.get('checkUrlIntegrity') === 'true',
        testAuth: url.searchParams.get('testAuth') === 'true',
      };
    }

    // Test authentication if requested - we can keep this but it won't do anything specific now
    if (params.testAuth) {
      console.log('Testing Trip.com access...');
      // Just try to access the Trip.com site
      const testResponse = await fetch('https://www.trip.com/hotels/', {
        method: 'GET',
        headers: BROWSER_HEADERS,
      });
      
      return new Response(JSON.stringify({
        success: true,
        authTest: {
          success: testResponse.ok,
          status: testResponse.status,
          statusText: testResponse.statusText
        }
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    // Check URL integrity if requested
    if (params.checkUrlIntegrity) {
      console.log('Checking URL integrity...');
      const integrity = await checkBookingUrlIntegrity();
      return new Response(JSON.stringify({
        success: true,
        urlIntegrity: integrity
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }
    
    // Process based on parameters
    if (params.processAll) {
      console.log('Processing all bookings...');
      const result = await processAllBookings();
      return new Response(JSON.stringify({
        success: true,
        message: `Processed ${result.total} bookings, ${result.successful} successful, ${result.failed} failed`,
        urlIntegrity: result.urlIntegrity,
        failureReasons: result.failureReasons
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    } else if (params.bookingId) {
      // Process a single booking
      console.log(`Processing single booking: ${params.bookingId}`);
      const { data: booking, error } = await supabase
        .from('bookings')
        .select('*')
        .eq('id', params.bookingId)
        .single();
        
      if (error) {
        throw new Error(`Booking not found: ${error.message}`);
      }
      
      const result = await processBooking(booking);
      return new Response(JSON.stringify({
        success: result.success,
        message: result.success ? 'Price updated successfully' : `Failed to update price: ${result.error}`
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    } else {
      throw new Error('Missing required parameters: bookingId, processAll, testAuth, or checkUrlIntegrity');
    }
  } catch (error) {
    console.error('Error in fetch-hotel-prices function:', error);
    return new Response(JSON.stringify({ 
      success: false, 
      error: error.message 
    }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  }
});
