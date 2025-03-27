
import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";
import * as cheerio from "https://esm.sh/cheerio@1.0.0-rc.12";

const BATCH_SIZE = 5;
const TEST_HOTEL_ID = "740887";
const DEBUG_HTML_LENGTH = 1000;
const PRICE_DEBUG_CONTEXT = 200; // Context length for price elements

const BROWSER_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
  "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
  "Accept-Language": "en-US,en;q=0.9",
  "Cache-Control": "no-cache",
  "Pragma": "no-cache",
};

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const supabaseUrl = Deno.env.get("SUPABASE_URL") as string;
const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") as string;
const supabase = createClient(supabaseUrl, supabaseKey);

function isValidUrl(urlString: string): boolean {
  try {
    if (!urlString.startsWith('http://') && !urlString.startsWith('https://')) {
      urlString = 'https://' + urlString;
    }
    
    const url = new URL(urlString);
    return true;
  } catch (error) {
    console.error(`Invalid URL: ${urlString}`, error.message);
    return false;
  }
}

function createTripUrl(
  hotelId: string = TEST_HOTEL_ID, 
  checkInDate: string, 
  checkOutDate: string, 
  groupAdults: number = 2,
  currency: string = "EUR"
): string {
  try {
    console.log(`Creating Trip.com URL for hotel ID: ${hotelId}`);
    
    const formatDate = (dateString: string): string => {
      const date = new Date(dateString);
      if (isNaN(date.getTime())) {
        throw new Error(`Invalid date: ${dateString}`);
      }
      return date.toISOString().split('T')[0];
    };

    const formattedCheckIn = formatDate(checkInDate);
    const formattedCheckOut = formatDate(checkOutDate);
    
    const url = `https://www.trip.com/hotels/detail/?hotelId=${hotelId}&checkIn=${formattedCheckIn}&checkOut=${formattedCheckOut}&adult=${groupAdults}&children=0&curr=${currency}`;
    
    console.log(`Final Trip.com URL: ${url}`);
    return url;
  } catch (error) {
    console.error('Error creating Trip.com URL:', error);
    throw new Error(`Failed to create Trip.com URL: ${error.message}`);
  }
}

function extractHotelId(url: string | null): string {
  if (!url) {
    console.log('No URL provided, using test hotel ID');
    return TEST_HOTEL_ID;
  }

  try {
    if (url.includes('trip.com') && url.includes('hotelId=')) {
      const regex = /hotelId=([0-9]+)/;
      const match = url.match(regex);
      if (match && match[1]) {
        console.log(`Extracted hotel ID from URL: ${match[1]}`);
        return match[1];
      }
    }
    
    console.log(`Could not extract hotel ID from URL: ${url}, using test hotel ID`);
    return TEST_HOTEL_ID;
  } catch (error) {
    console.error('Error extracting hotel ID:', error);
    return TEST_HOTEL_ID;
  }
}

async function fetchHotelPrice(
  tripUrl: string,
  booking: any
): Promise<{price: number | null, error?: string}> {
  try {
    console.log(`Fetching price for booking ${booking.id} with URL: ${tripUrl}`);
    
    const response = await fetch(tripUrl, {
      method: 'GET',
      headers: BROWSER_HEADERS,
    });
    
    console.log(`Response for booking ${booking.id}: status: ${response.status}, statusText: ${response.statusText}`);
    
    if (!response.ok) {
      return {price: null, error: `HTTP error: ${response.status} ${response.statusText}`};
    }

    const html = await response.text();
    
    if (!html || html.trim().length === 0) {
      return {price: null, error: 'Empty response received'};
    }
    
    const $ = cheerio.load(html);
    
    console.log(`Received HTML length: ${html.length} characters`);
    
    let prices: number[] = [];
    
    // Specific patterns based on the observed HTML structure
    const tripRegexPatterns = [
      /Total price:\s*[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/g,  // Prioritize exact match for "Total price: €XXX" format
      /Total\s*[Pp]rice:?\s*[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/g,
      /Total\s*[Pp]rice:?\s*(?:€|EUR|USD|\$)\s*(\d+(?:,\d+)*(?:\.\d+)?)/g,
      /Total\s*[Pp]rice\s*[^\d]*?(\d+(?:[,.]\d+)?)/gi,
      /Total\s*[Pp]rice<\/?[^>]*>[^<]*?[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/g,
      /Total\s*[Pp]rice<\/?[^>]*>[^<]*?(\d+(?:,\d+)*(?:\.\d+)?)\s*[€$£¥]/g,
      /Total\s*[Pp]rice[^\d]*?[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/g
    ];
    
    // Trip.com price-specific class selectors (based on the example HTML)
    const tripSpecificSelectors = [
      '.saleRoomItemBox-priceBox-priceExplain__PPb0f div',
      '[class*="priceExplain"] div',
      '[class*="price-explain"] div',
      '[class*="totalPrice"] div',
      '[class*="total-price"] div',
      '[class*="totalAmount"] div',
      '.m-hotel-price-container',
      '.J_PriceInfo',
      '.m-hotel-low-price',
      '.low-price-value',
      '.card-price-content',
      '.card-price-wrap'
    ];
    
    console.log(`Searching for Trip.com specific price elements...`);
    
    // First, try the most specific selectors
    for (const selector of tripSpecificSelectors) {
      const elements = $(selector);
      if (elements.length > 0) {
        console.log(`Found ${elements.length} elements with selector "${selector}"`);
        
        elements.each((i, el) => {
          const text = $(el).text().trim();
          
          // Log the element text for debugging
          console.log(`${selector} element ${i}: "${text}"`);
          
          // Specifically look for elements with "Total price:" text
          if (text.includes('Total price:')) {
            console.log(`Found element with "Total price:" text: "${text}"`);
            
            // Try each regex pattern
            for (const pattern of tripRegexPatterns) {
              pattern.lastIndex = 0;
              const match = pattern.exec(text);
              if (match && match[1]) {
                const cleanPrice = match[1].replace(/,/g, '');
                const price = parseFloat(cleanPrice);
                
                if (!isNaN(price) && price > 0) {
                  console.log(`Successfully extracted price from "Total price:" element: ${price}`);
                  prices.push(price);
                }
              }
            }
          }
          
          // Also check for any element that contains a currency symbol followed by a number
          const currencyRegex = /[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/;
          const currencyMatch = text.match(currencyRegex);
          
          if (currencyMatch && currencyMatch[1]) {
            const cleanPrice = currencyMatch[1].replace(/,/g, '');
            const price = parseFloat(cleanPrice);
            
            if (!isNaN(price) && price > 0) {
              console.log(`Found currency symbol with number in element: ${price}`);
              prices.push(price);
            }
          }
        });
      }
    }
    
    // If we still don't have prices, try more general selectors
    if (prices.length === 0) {
      console.log(`No prices found with specific selectors, trying more general approach...`);
      
      // Target elements with common price-related class names
      const priceClasses = [
        '[class*="price"]',
        '[class*="Price"]',
        '[class*="cost"]',
        '[class*="Cost"]',
        '[class*="total"]',
        '[class*="Total"]',
        '[class*="amount"]',
        '[class*="Amount"]'
      ];
      
      // Search for any elements with these classes
      for (const selector of priceClasses) {
        if (prices.length > 0) break; // Stop if we've found prices
        
        const elements = $(selector);
        console.log(`Found ${elements.length} elements with selector "${selector}"`);
        
        elements.each((i, el) => {
          if (i < 15) { // Limit to first 15 elements to avoid excessive logging
            const text = $(el).text().trim();
            
            // Skip empty text
            if (!text) return;
            
            // Skip very long text (likely not a price)
            if (text.length > 100) {
              console.log(`Skipping long text (${text.length} chars) for ${selector} element ${i}`);
              return;
            }
            
            console.log(`${selector} element ${i}: "${text}"`);
            
            // Check for "Total price:" pattern
            if (text.includes('Total price:')) {
              console.log(`Found element with "Total price:" text: "${text}"`);
              
              // Extract price using regex
              const totalPriceRegex = /Total price:\s*[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/;
              const match = text.match(totalPriceRegex);
              
              if (match && match[1]) {
                const cleanPrice = match[1].replace(/,/g, '');
                const price = parseFloat(cleanPrice);
                
                if (!isNaN(price) && price > 0) {
                  console.log(`Successfully extracted price from "Total price:" element: ${price}`);
                  prices.push(price);
                }
              }
            }
            
            // Check for currency symbol with number
            const currencyRegex = /[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/;
            const currencyMatch = text.match(currencyRegex);
            
            if (currencyMatch && currencyMatch[1]) {
              const cleanPrice = currencyMatch[1].replace(/,/g, '');
              const price = parseFloat(cleanPrice);
              
              if (!isNaN(price) && price > 0) {
                console.log(`Found currency symbol with number in element: ${price}`);
                prices.push(price);
              }
            }
          }
        });
      }
    }
    
    // If still no prices, try specific keywords in text
    if (prices.length === 0) {
      console.log(`No prices found in price-related elements, searching for specific texts...`);
      
      // Look for elements containing "Total price:" text
      $('*:contains("Total price:")').each((i, el) => {
        const text = $(el).text().trim();
        
        // Skip if the element text is too long (likely not a direct price container)
        if (text.length > 100) return;
        
        console.log(`Found element containing "Total price:" text: "${text}"`);
        
        const totalPriceRegex = /Total price:\s*[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/;
        const match = text.match(totalPriceRegex);
        
        if (match && match[1]) {
          const cleanPrice = match[1].replace(/,/g, '');
          const price = parseFloat(cleanPrice);
          
          if (!isNaN(price) && price > 0) {
            console.log(`Successfully extracted price from "Total price:" element: ${price}`);
            prices.push(price);
          }
        }
      });
      
      // Also look for elements containing currency symbols
      $('*:contains("€"), *:contains("$"), *:contains("£"), *:contains("¥")').each((i, el) => {
        // Skip if we've already found prices
        if (prices.length > 0) return;
        
        const text = $(el).text().trim();
        
        // Skip if the element text is too long
        if (text.length > 100) return;
        
        // Skip if it doesn't look like a price (contains some key indicators)
        if (!text.includes('price') && !text.includes('total') && !text.includes('amount') && 
            !text.includes('cost') && !text.includes('€') && !text.includes('$') && 
            !text.includes('£') && !text.includes('¥')) return;
        
        console.log(`Found element containing currency symbol: "${text}"`);
        
        const currencyRegex = /[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/;
        const match = text.match(currencyRegex);
        
        if (match && match[1]) {
          const cleanPrice = match[1].replace(/,/g, '');
          const price = parseFloat(cleanPrice);
          
          if (!isNaN(price) && price > 0) {
            console.log(`Extracted price from currency element: ${price}`);
            prices.push(price);
          }
        }
      });
    }
    
    // Last resort: look for the HTML pattern from the example
    if (prices.length === 0) {
      console.log(`Using fallback pattern matching for price extraction...`);
      
      // Create a pattern that matches the HTML structure from the example
      const pattern = /<div class="saleRoomItemBox-priceBox-priceExplain__PPb0f"><div>Total price: [€$£¥](\d+)<\/div>/;
      const match = html.match(pattern);
      
      if (match && match[1]) {
        const price = parseFloat(match[1]);
        if (!isNaN(price) && price > 0) {
          console.log(`Found price using direct HTML pattern match: ${price}`);
          prices.push(price);
        }
      }
      
      // Also check for a more general pattern
      const generalPattern = /<div[^>]*>Total price: [€$£¥](\d+(?:,\d+)*(?:\.\d+)?)<\/div>/g;
      let generalMatch;
      while ((generalMatch = generalPattern.exec(html)) !== null) {
        if (generalMatch[1]) {
          const cleanPrice = generalMatch[1].replace(/,/g, '');
          const price = parseFloat(cleanPrice);
          if (!isNaN(price) && price > 0) {
            console.log(`Found price using general HTML pattern match: ${price}`);
            prices.push(price);
          }
        }
      }
    }
    
    // Validate and return the extracted prices
    if (prices.length > 0) {
      prices.sort((a, b) => a - b);
      console.log(`Found ${prices.length} prices: ${prices.join(', ')}`);
      
      const cheapestPrice = prices[0];
      console.log(`Cheapest price for booking ${booking.id}: ${cheapestPrice}`);
      return { price: cheapestPrice };
    } else {
      if (Deno.env.get("STAGE") === "development") {
        const randomPrice = Math.floor(Math.random() * 500) + 100;
        console.log(`Development mode: Returning random price: ${randomPrice}`);
        return { price: randomPrice };
      }
      
      console.log(`No prices found for booking ${booking.id}`);
      return { price: null, error: 'No prices found on the page' };
    }
  } catch (error) {
    console.error(`Error fetching hotel price for booking ${booking.id}:`, error);
    return { price: null, error: `Error fetching hotel price: ${error.message}` };
  }
}

async function processBooking(booking: any): Promise<{success: boolean, error?: string}> {
  try {
    console.log(`Processing booking ${booking.id}`);
    
    let tripUrl: string;
    let hotelId: string;
    
    if (booking.trip_url) {
      tripUrl = booking.trip_url;
      console.log(`Using stored Trip.com URL for booking ${booking.id}: ${tripUrl}`);
      
      hotelId = extractHotelId(tripUrl);
    } else {
      hotelId = extractHotelId(booking.hotel_url);
      
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
      
      const { error: updateUrlError } = await supabase
        .from('bookings')
        .update({
          trip_url: tripUrl,
          trip_hotel_id: hotelId
        })
        .eq('id', booking.id);
        
      if (updateUrlError) {
        console.error(`Error updating Trip.com URL for booking ${booking.id}:`, updateUrlError);
        // Continue anyway, as this is not critical
      } else {
        console.log(`Stored Trip.com URL and hotel ID for booking ${booking.id}`);
      }
    }

    const {price, error} = await fetchHotelPrice(tripUrl, booking);
    
    if (price === null) {
      console.log(`Could not fetch price for booking ${booking.id}: ${error}`);
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

async function processAllBookings(): Promise<{ 
  total: number, 
  successful: number, 
  failed: number,
  failureReasons: Record<string, number>
}> {
  try {
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
        failureReasons: {}
      };
    }

    if (!bookings || bookings.length === 0) {
      console.log('No active bookings found');
      return { 
        total: 0, 
        successful: 0, 
        failed: 0, 
        failureReasons: {}
      };
    }

    console.log(`Processing ${bookings.length} bookings`);
    
    let successful = 0;
    let failed = 0;
    const failureReasons: Record<string, number> = {};
    
    for (let i = 0; i < bookings.length; i += BATCH_SIZE) {
      const batch = bookings.slice(i, i + BATCH_SIZE);
      
      const results = await Promise.all(
        batch.map(booking => processBooking(booking))
      );
      
      results.forEach(result => {
        if (result.success) {
          successful++;
        } else {
          failed++;
          const reason = result.error || "Unknown error";
          failureReasons[reason] = (failureReasons[reason] || 0) + 1;
        }
      });
      
      if (i + BATCH_SIZE < bookings.length) {
        console.log(`Processed batch ${i / BATCH_SIZE + 1}/${Math.ceil(bookings.length / BATCH_SIZE)}, adding delay before next batch`);
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }

    if (failed > 0) {
      console.log('Failure reasons:', failureReasons);
    }

    return { 
      total: bookings.length, 
      successful, 
      failed,
      failureReasons
    };
  } catch (error) {
    console.error('Error processing bookings:', error);
    return { 
      total: 0, 
      successful: 0, 
      failed: 0, 
      failureReasons: {'Unhandled exception': 1}
    };
  }
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
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
        testAuth: url.searchParams.get('testAuth') === 'true',
      };
    }

    if (params.testAuth) {
      console.log('Testing Trip.com access...');
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
    
    if (params.processAll) {
      console.log('Processing all bookings...');
      const result = await processAllBookings();
      return new Response(JSON.stringify({
        success: true,
        message: `Processed ${result.total} bookings, ${result.successful} successful, ${result.failed} failed`,
        failureReasons: result.failureReasons
      }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    } else if (params.bookingId) {
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
      throw new Error('Missing required parameters: bookingId, processAll, or testAuth');
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
