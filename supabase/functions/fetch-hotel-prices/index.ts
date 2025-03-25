
import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";

// Constants and configuration
const BOOKING_COM_GRAPHQL_ENDPOINT = "https://www.booking.com/dml/graphql";
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 2000;
const BATCH_SIZE = 5; // Process bookings in batches to avoid rate limiting

// Headers to mimic a browser request
const BROWSER_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
  "Accept": "application/json",
  "Accept-Language": "en-US,en;q=0.9",
  "Content-Type": "application/json",
  "Origin": "https://www.booking.com",
  "Referer": "https://www.booking.com/",
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

// GraphQL query to fetch hotel prices
const PRICE_QUERY = `
  query SearchQueries($input: PropertyCardSearchInput!) {
    propertyCards(input: $input) {
      cards {
        __typename
        priceInfo {
          displayPrice {
            perStay {
              amount
              currency
              value
            }
          }
        }
      }
    }
  }
`;

// Helper function to validate URL
function isValidUrl(urlString: string): boolean {
  try {
    // Ensure URL has a protocol
    if (!urlString.startsWith('http://') && !urlString.startsWith('https://')) {
      urlString = 'https://' + urlString;
    }
    
    const url = new URL(urlString);
    return url.hostname.includes('booking.com'); // Ensure it's a booking.com URL
  } catch (error) {
    console.error(`Invalid URL: ${urlString}`, error.message);
    return false;
  }
}

// Helper function to create booking.com search URL with query parameters
function createBookingUrl(
  hotelUrl: string, 
  checkInDate: string, 
  checkOutDate: string, 
  groupAdults: number = 2
): string {
  try {
    console.log(`Creating booking URL from: ${hotelUrl}`);
    
    // Validate the hotel URL first
    if (!isValidUrl(hotelUrl)) {
      throw new Error(`Invalid hotel URL: ${hotelUrl}`);
    }

    // Ensure URL has a protocol
    if (!hotelUrl.startsWith('http://') && !hotelUrl.startsWith('https://')) {
      hotelUrl = 'https://' + hotelUrl;
    }
    
    // Format dates for booking.com (YYYY-MM-DD)
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
    
    // Create a URL object to ensure proper URL manipulation
    let baseUrl: URL;
    try {
      baseUrl = new URL(hotelUrl);
    } catch (error) {
      throw new Error(`Failed to parse hotel URL: ${hotelUrl}`);
    }
    
    // Add parameters to URL
    baseUrl.searchParams.set('checkin', formattedCheckIn);
    baseUrl.searchParams.set('checkout', formattedCheckOut);
    baseUrl.searchParams.set('group_adults', groupAdults.toString());
    
    const finalUrl = baseUrl.toString();
    console.log(`Final booking URL: ${finalUrl}`);
    
    // Return the complete URL
    return finalUrl;
  } catch (error) {
    console.error('Error creating booking URL:', error);
    throw new Error(`Failed to create booking URL: ${error.message}`);
  }
}

// Helper function to extract hotel ID from URL
function extractHotelId(url: string): string | null {
  try {
    if (!url) {
      console.error('Empty URL provided to extractHotelId');
      return null;
    }

    // Ensure URL has a protocol for parsing
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://' + url;
    }

    console.log(`Extracting hotel ID from URL: ${url}`);
    
    // Try to extract ID from URL patterns like /hotel/us/name.en-us.html or /hotel/name.html
    const regex = /\/hotel\/(?:[a-z]{2}\/)?([^.]+)(?:\.[a-z-]+)?\.html/;
    const match = url.match(regex);
    
    if (match) {
      console.log(`Extracted hotel ID: ${match[1]}`);
      return match[1];
    }
    
    // If regex doesn't match, try to get from path segments
    try {
      const urlObj = new URL(url);
      const pathSegments = urlObj.pathname.split('/').filter(Boolean);
      
      // Check if this is a hotel page path
      if (pathSegments.includes('hotel')) {
        const hotelIdIndex = pathSegments.indexOf('hotel') + 2; // +2 to account for possible country code
        if (hotelIdIndex < pathSegments.length) {
          const potentialId = pathSegments[hotelIdIndex].split('.')[0];
          console.log(`Extracted hotel ID from path: ${potentialId}`);
          return potentialId;
        }
      }
    } catch (parseError) {
      console.error('Error parsing URL in extractHotelId:', parseError);
    }
    
    console.error('Could not extract hotel ID from URL:', url);
    return null;
  } catch (error) {
    console.error('Error extracting hotel ID:', error);
    return null;
  }
}

// Function to fetch price from Booking.com using GraphQL
async function fetchHotelPrice(
  bookingUrl: string,
  retryCount = 0
): Promise<number | null> {
  try {
    console.log(`Fetching price for URL: ${bookingUrl}`);
    
    // Validate the booking URL
    if (!isValidUrl(bookingUrl)) {
      console.error(`Invalid booking URL: ${bookingUrl}`);
      return null;
    }

    // Ensure URL has a protocol
    if (!bookingUrl.startsWith('http://') && !bookingUrl.startsWith('https://')) {
      bookingUrl = 'https://' + bookingUrl;
    }
    
    // Parse URL to get necessary parameters
    let url: URL;
    try {
      url = new URL(bookingUrl);
    } catch (error) {
      console.error(`Invalid URL format: ${bookingUrl}`, error);
      return null;
    }
    
    const hotelId = extractHotelId(bookingUrl);
    
    if (!hotelId) {
      console.error(`Could not extract hotel ID from URL: ${bookingUrl}`);
      return null;
    }

    // Get check-in/check-out dates from URL
    const checkin = url.searchParams.get('checkin');
    const checkout = url.searchParams.get('checkout');
    const group_adults = parseInt(url.searchParams.get('group_adults') || '2');
    
    if (!checkin || !checkout) {
      console.error(`Missing check-in/check-out dates in URL: ${bookingUrl}`);
      return null;
    }

    // Prepare GraphQL request
    const graphqlInput = {
      input: {
        nrAdults: group_adults,
        nrChildren: 0,
        checkin: checkin,
        checkout: checkout,
        childrenAges: [],
        filters: {
          idFilters: [{ distance: 0, id: hotelId, type: "HOTEL" }],
        },
        optionalFeatures: {
          useAvailability: true,
        },
      }
    };

    console.log(`GraphQL request payload:`, JSON.stringify(graphqlInput, null, 2));

    // Make GraphQL request
    const response = await fetch(BOOKING_COM_GRAPHQL_ENDPOINT, {
      method: 'POST',
      headers: BROWSER_HEADERS,
      body: JSON.stringify({
        operationName: 'SearchQueries',
        query: PRICE_QUERY,
        variables: graphqlInput
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const data = await response.json();
    
    // Log the response structure for debugging
    console.log('GraphQL response cards length:', data?.data?.propertyCards?.cards?.length || 0);
    
    // Extract the price from the response
    const cards = data?.data?.propertyCards?.cards;
    if (!cards || !cards.length) {
      console.error('No property cards found in response');
      return null;
    }

    const price = cards[0]?.priceInfo?.displayPrice?.perStay?.value;
    if (typeof price === 'number') {
      console.log(`Successfully extracted price: ${price}`);
      return price;
    }
    
    console.error('Price not found in response structure:', JSON.stringify(cards[0]?.priceInfo || 'No priceInfo'));
    return null;
  } catch (error) {
    console.error(`Error fetching hotel price: ${error.message}`);
    
    // Implement retry logic
    if (retryCount < MAX_RETRIES) {
      console.log(`Retrying (${retryCount + 1}/${MAX_RETRIES}) after ${RETRY_DELAY_MS}ms...`);
      await new Promise(resolve => setTimeout(resolve, RETRY_DELAY_MS));
      return fetchHotelPrice(bookingUrl, retryCount + 1);
    }
    
    return null;
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
async function processBooking(booking: any): Promise<boolean> {
  try {
    if (!booking.hotel_url) {
      console.log(`Booking ${booking.id} has no hotel_url, skipping`);
      return false;
    }

    console.log(`Processing booking ${booking.id} with URL: ${booking.hotel_url}`);
    
    // Validate hotel_url format before proceeding
    if (!isValidUrl(booking.hotel_url)) {
      console.error(`Invalid hotel_url format for booking ${booking.id}: ${booking.hotel_url}`);
      return false;
    }

    // Create the complete booking URL with dates and adults
    let bookingUrl: string;
    try {
      bookingUrl = createBookingUrl(
        booking.hotel_url,
        booking.check_in_date,
        booking.check_out_date,
        booking.group_adults || 2
      );
    } catch (error) {
      console.error(`Failed to create booking URL for booking ${booking.id}:`, error);
      return false;
    }

    // Fetch the price
    const price = await fetchHotelPrice(bookingUrl);
    
    if (price === null) {
      console.log(`Could not fetch price for booking ${booking.id}`);
      return false;
    }

    // Update the booking with the fetched price
    const { error } = await supabase
      .from('bookings')
      .update({
        fetched_price: price,
        fetched_price_updated_at: new Date().toISOString()
      })
      .eq('id', booking.id);

    if (error) {
      console.error(`Error updating booking ${booking.id}:`, error);
      return false;
    }

    console.log(`Successfully updated booking ${booking.id} with price ${price}`);
    return true;
  } catch (error) {
    console.error(`Error processing booking ${booking.id}:`, error);
    return false;
  }
}

// Function to fetch and process bookings in batches
async function processAllBookings(): Promise<{ total: number, successful: number, urlIntegrity: any }> {
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
      return { total: 0, successful: 0, urlIntegrity };
    }

    if (!bookings || bookings.length === 0) {
      console.log('No active bookings found');
      return { total: 0, successful: 0, urlIntegrity };
    }

    console.log(`Processing ${bookings.length} bookings`);
    
    // Process bookings in batches to avoid rate limiting
    let successful = 0;
    
    for (let i = 0; i < bookings.length; i += BATCH_SIZE) {
      const batch = bookings.slice(i, i + BATCH_SIZE);
      
      // Process batch in parallel
      const results = await Promise.all(
        batch.map(booking => processBooking(booking))
      );
      
      // Count successful updates
      successful += results.filter(Boolean).length;
      
      // Add delay between batches to avoid rate limiting
      if (i + BATCH_SIZE < bookings.length) {
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }

    return { total: bookings.length, successful, urlIntegrity };
  } catch (error) {
    console.error('Error processing bookings:', error);
    return { total: 0, successful: 0, urlIntegrity: { valid: 0, invalid: 0, invalidUrls: [] } };
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
      params = await req.json();
    } else {
      const url = new URL(req.url);
      params = {
        bookingId: url.searchParams.get('bookingId'),
        processAll: url.searchParams.get('processAll') === 'true',
        checkUrlIntegrity: url.searchParams.get('checkUrlIntegrity') === 'true',
      };
    }

    // Check URL integrity if requested
    if (params.checkUrlIntegrity) {
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
      const result = await processAllBookings();
      return new Response(JSON.stringify({
        success: true,
        message: `Processed ${result.total} bookings, ${result.successful} successful`,
        urlIntegrity: result.urlIntegrity
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    } else if (params.bookingId) {
      // Process a single booking
      const { data: booking, error } = await supabase
        .from('bookings')
        .select('*')
        .eq('id', params.bookingId)
        .single();
        
      if (error) {
        throw new Error(`Booking not found: ${error.message}`);
      }
      
      const success = await processBooking(booking);
      return new Response(JSON.stringify({
        success,
        message: success ? 'Price updated successfully' : 'Failed to update price'
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    } else {
      throw new Error('Missing required parameters: bookingId, processAll, or checkUrlIntegrity');
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
