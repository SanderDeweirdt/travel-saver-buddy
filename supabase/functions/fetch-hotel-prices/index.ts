import "https://deno.land/x/xhr@0.1.0/mod.ts";
import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.38.4";
import * as cheerio from "https://esm.sh/cheerio@1.0.0-rc.12";

const BATCH_SIZE = 5;
const TEST_HOTEL_ID = "740887";
const DEBUG_HTML_LENGTH = 1000;

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
    
    const regexPatterns = [
      /[Tt]otal\s*[Pp]rice:?\s*[€$£¥](\d+(?:\.\d+)?)/g,
      /[Pp]rice:?\s*[€$£¥](\d+(?:\.\d+)?)/g,
      /[€$£¥]\s*(\d+(?:,\d+)*(?:\.\d+)?)/g,
      /(\d+(?:,\d+)*(?:\.\d+)?)\s*[€$£¥]/g,
      /[€$£¥](\d+(?:,\d+)*(?:\.\d+)?)\s*(?:per\s+night|\/\s*night)/gi,
      /(\d+(?:,\d+)*(?:\.\d+)?)\s*EUR/gi,
      /[€$£¥]\s*(\d+(?:\.\d+)?(?:,\d+)?)/g
    ];
    
    if (Deno.env.get("STAGE") === "development") {
      console.log(`HTML sample (first ${DEBUG_HTML_LENGTH} chars): ${html.substring(0, DEBUG_HTML_LENGTH)}`);
      
      console.log("Searching for price elements in HTML...");
      
      const priceElements = $('[class*="price"], [id*="price"], [class*="Price"], [id*="Price"]');
      console.log(`Found ${priceElements.length} elements with "price" in class or id`);
      priceElements.each((i, el) => {
        if (i < 10) {
          console.log(`Price element ${i}: ${$(el).text().trim()}`);
          console.log(`Element HTML: ${$.html(el).substring(0, 200)}`);
        }
      });
      
      console.log("Searching for Trip.com specific price containers...");
      
      const tripPriceSelectors = [
        '.price-info', '.actual-price', '.m-price', '.price', '.J_PriceInfo',
        '.J_HotelPriceInfo', '.J_RoomPriceInfo', '.price_num', '.price-tag'
      ];
      
      tripPriceSelectors.forEach(selector => {
        const elements = $(selector);
        if (elements.length > 0) {
          console.log(`Found ${elements.length} elements with selector "${selector}"`);
          elements.each((i, el) => {
            if (i < 3) {
              console.log(`${selector} element ${i} text: ${$(el).text().trim()}`);
              console.log(`${selector} element ${i} HTML: ${$.html(el).substring(0, 200)}`);
            }
          });
        }
      });
    }
    
    const bodyText = $('body').text();
    
    const priceContainers = [
      '.J_HotelPriceInfo', '.actual-price', '.m-price', '.price-info',
      '.J_PriceSection', '.price_num', '.js-hotel-price'
    ];
    
    let foundInContainer = false;
    
    priceContainers.forEach(container => {
      if (foundInContainer) return;
      
      const priceEls = $(container);
      if (priceEls.length > 0) {
        console.log(`Found ${priceEls.length} elements with selector "${container}"`);
        
        priceEls.each((i, el) => {
          const priceText = $(el).text().trim();
          console.log(`Price container ${container} - element ${i} text: ${priceText}`);
          
          for (const pattern of regexPatterns) {
            pattern.lastIndex = 0;
            let match;
            while ((match = pattern.exec(priceText)) !== null) {
              if (match[1]) {
                const cleanPrice = match[1].replace(/,/g, '');
                const price = parseFloat(cleanPrice);
                
                if (!isNaN(price) && price > 0) {
                  console.log(`Found price in ${container}: ${price} (matched with ${pattern})`);
                  prices.push(price);
                  foundInContainer = true;
                }
              }
            }
          }
        });
      }
    });
    
    if (prices.length === 0) {
      for (const pattern of regexPatterns) {
        pattern.lastIndex = 0;
        let match;
        while ((match = pattern.exec(bodyText)) !== null) {
          if (match[1]) {
            const cleanPrice = match[1].replace(/,/g, '');
            const price = parseFloat(cleanPrice);
            
            if (!isNaN(price) && price > 0) {
              prices.push(price);
              console.log(`Found price with pattern ${pattern}: ${price}`);
            }
          }
        }
        
        if (prices.length > 0) {
          console.log(`Found ${prices.length} prices using pattern: ${pattern}`);
          break;
        }
      }
    }
    
    if (prices.length === 0) {
      console.log('No price matches found using regex patterns, trying direct element search');
      
      $('div:contains("Total price"), span:contains("Total price"), div:contains("price"), span:contains("price")').each((_i, el) => {
        const text = $(el).text();
        console.log(`Checking element text: ${text.substring(0, 100)}`);
        
        for (const pattern of regexPatterns) {
          pattern.lastIndex = 0;
          let match;
          while ((match = pattern.exec(text)) !== null) {
            if (match[1]) {
              const cleanPrice = match[1].replace(/,/g, '');
              const price = parseFloat(cleanPrice);
              
              if (!isNaN(price) && price > 0) {
                prices.push(price);
                console.log(`Found price in element: ${price} (from text: ${text.trim().substring(0, 30)}...)`);
              }
            }
          }
        }
      });
    }
    
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
