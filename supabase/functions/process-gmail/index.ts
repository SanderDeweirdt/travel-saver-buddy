
import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.49.1';

// Required for CORS
const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Initialize Supabase client
const supabaseUrl = Deno.env.get('SUPABASE_URL') || '';
const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || '';
const supabase = createClient(supabaseUrl, supabaseKey);

interface GmailMessage {
  id: string;
  threadId: string;
  labelIds: string[];
  snippet: string;
  payload: {
    partId?: string;
    mimeType: string;
    filename?: string;
    headers: { name: string; value: string }[];
    body: {
      attachmentId?: string;
      size: number;
      data?: string;
    };
    parts?: any[];
  };
  sizeEstimate: number;
  historyId: string;
  internalDate: string;
}

interface ParsingRules {
  match: {
    from: string;
    subjectContains: string;
  };
  extract: {
    confirmation_number: string;
    hotel_name: string;
    hotel_url: string;
    price_paid: string;
    room_type: string;
    check_in_date_raw?: string;
    check_out_date_raw?: string;
    cancellation_date_raw?: string;
    check_in_date?: string;
    check_out_date?: string;
    cancellation_date?: string;
  };
}

interface BookingInfo {
  booking_reference: string;
  hotel_name: string;
  hotel_url: string | null;
  price_paid: number;
  room_type: string | null;
  check_in_date: string;
  check_out_date: string;
  cancellation_date: string;
  email_id: string;
  currency: string;
  cancellation_policy?: string;
  source: string;
  imported_from_gmail: boolean;
  import_timestamp: string;
}

// Extract hotel information from HTML content
function extractHotelInfoFromHtml(htmlContent: string): { hotelName: string | null; hotelUrl: string | null } {
  try {
    console.log("Extracting hotel info from HTML content");
    
    // Look for anchor tags with hotel links
    const hotelAnchorRegex = /<a\s+[^>]*?href=["']([^"']*?\/hotel\/[^"']*?)["'][^>]*?>([^<]+)<\/a>/i;
    const match = htmlContent.match(hotelAnchorRegex);
    
    if (match && match[1] && match[2]) {
      console.log("Found hotel anchor tag:", match[0]);
      return {
        hotelUrl: match[1],
        hotelName: match[2].trim()
      };
    }
    
    // Fallback: look for any booking.com hotel URLs
    const hotelUrlRegex = /https:\/\/www\.booking\.com\/hotel\/[^"'\s]+\.html/i;
    const urlMatch = htmlContent.match(hotelUrlRegex);
    
    if (urlMatch && urlMatch[0]) {
      console.log("Found hotel URL in text:", urlMatch[0]);
      // Extract hotel name from URL slug
      const hotelNameFromUrl = extractHotelNameFromUrl(urlMatch[0]);
      return {
        hotelUrl: urlMatch[0],
        hotelName: hotelNameFromUrl
      };
    }
    
    return { hotelName: null, hotelUrl: null };
  } catch (error) {
    console.error("Error extracting hotel info from HTML:", error);
    return { hotelName: null, hotelUrl: null };
  }
}

// Extract hotel name from URL slug
function extractHotelNameFromUrl(url: string): string {
  try {
    // Extract the slug part
    const urlPath = url.split('/hotel/')[1];
    if (!urlPath) return "Unknown Hotel";
    
    // Get the last part of the URL path which usually contains the hotel name
    let hotelSlug = "";
    if (urlPath.includes('/')) {
      // If there are more path segments, get the last one
      const segments = urlPath.split('/');
      hotelSlug = segments[segments.length - 1].split('.html')[0];
    } else {
      hotelSlug = urlPath.split('.html')[0];
    }
    
    // Special case for a&o hotels
    hotelSlug = hotelSlug.replace(/aundo/g, "a&o");
    
    // Convert slug to readable name
    return hotelSlug
      .split('-')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  } catch (error) {
    console.error("Error extracting hotel name from URL:", error);
    return "Unknown Hotel";
  }
}

// Extract booking information from email content using the provided parsing rules
function extractBookingInfo(body: string, emailId: string, parsingRules?: ParsingRules): BookingInfo | null {
  try {
    console.log("Extracting booking info from email");
    
    // Check if content is HTML
    const isHtml = body.includes('<html') || body.includes('<body') || body.includes('<div') || body.includes('<a ');
    console.log("Content appears to be HTML:", isHtml);
    
    // Try to extract hotel information from HTML first
    let hotelInfo = { hotelName: null, hotelUrl: null };
    if (isHtml) {
      hotelInfo = extractHotelInfoFromHtml(body);
      console.log("Extracted hotel info from HTML:", hotelInfo);
    }
    
    // Define regex patterns based on provided parsing rules or use defaults
    const extractRegex = (pattern: string): RegExp => {
      const regexPattern = pattern.replace('regex:', '');
      return new RegExp(regexPattern, 'i');
    };
    
    let bookingRefRegex: RegExp;
    let hotelNameRegex: RegExp; 
    let hotelNameFallbackRegex: RegExp = /(.*?) is expecting you/i;
    let roomTypeRegex: RegExp;
    let checkInRegex: RegExp;
    let checkOutRegex: RegExp;
    let cancellationRegex: RegExp;
    let priceRegex: RegExp;
    let hotelUrlRegex: RegExp;
    let cancellationPolicyRegex: RegExp = /Free cancellation until ([^<]+)/i;
    
    if (parsingRules) {
      bookingRefRegex = extractRegex(parsingRules.extract.confirmation_number);
      hotelNameRegex = extractRegex(parsingRules.extract.hotel_name);
      roomTypeRegex = extractRegex(parsingRules.extract.room_type);
      
      // Handle both raw date formats and direct date formats
      checkInRegex = parsingRules.extract.check_in_date_raw 
        ? extractRegex(parsingRules.extract.check_in_date_raw)
        : (parsingRules.extract.check_in_date 
          ? extractRegex(parsingRules.extract.check_in_date) 
          : /Check-in\s*\w+,\s*(\w+ \d{1,2}, \d{4})/i);
          
      checkOutRegex = parsingRules.extract.check_out_date_raw 
        ? extractRegex(parsingRules.extract.check_out_date_raw)
        : (parsingRules.extract.check_out_date 
          ? extractRegex(parsingRules.extract.check_out_date) 
          : /Check-out\s*\w+,\s*(\w+ \d{1,2}, \d{4})/i);
          
      cancellationRegex = parsingRules.extract.cancellation_date_raw 
        ? extractRegex(parsingRules.extract.cancellation_date_raw)
        : (parsingRules.extract.cancellation_date 
          ? extractRegex(parsingRules.extract.cancellation_date) 
          : /cancel for FREE until\s*(\w+ \d{1,2}, \d{4} \d{2}:\d{2} [AP]M)/i);
          
      priceRegex = extractRegex(parsingRules.extract.price_paid);
      
      // Enhanced hotel URL extraction
      if (parsingRules.extract.hotel_url.includes("linkContains:/hotel/")) {
        hotelUrlRegex = /https:\/\/www\.booking\.com\/hotel\/[^\s"\)]+/i;
      } else {
        hotelUrlRegex = extractRegex(parsingRules.extract.hotel_url);
      }
    } else {
      // Default patterns
      bookingRefRegex = /Confirmation:\s*(\d+)/i;
      hotelNameRegex = /Your booking is confirmed at\s*(.*)/i;
      roomTypeRegex = /Your reservation\s*\d+ night[s]*,\s*(.*?)\n/i;
      checkInRegex = /Check-in\s*\w+,\s*(\w+ \d{1,2}, \d{4})/i;
      checkOutRegex = /Check-out\s*\w+,\s*(\w+ \d{1,2}, \d{4})/i;
      cancellationRegex = /cancel for FREE until\s*(\w+ \d{1,2}, \d{4} \d{2}:\d{2} [AP]M)/i;
      priceRegex = /Total price<\/div>\s*<div><span>€\s*(\d+\.\d{2})<\/span>/i;
      hotelUrlRegex = /https:\/\/www\.booking\.com\/hotel\/[^\s"\)]+/i;
    }

    // Match the patterns in the email body
    const bookingRefMatch = body.match(bookingRefRegex);
    const hotelNameMatch = body.match(hotelNameRegex);
    const hotelNameFallbackMatch = body.match(hotelNameFallbackRegex);
    const roomTypeMatch = body.match(roomTypeRegex);
    const checkInMatch = body.match(checkInRegex);
    const checkOutMatch = body.match(checkOutRegex);
    const cancellationMatch = body.match(cancellationRegex);
    const priceMatch = body.match(priceRegex);
    const hotelUrlMatch = !hotelInfo.hotelUrl ? body.match(hotelUrlRegex) : null;
    const cancellationPolicyMatch = body.match(cancellationPolicyRegex);

    // Parse the dates with timezone conversion to CET/CEST (+01:00)
    const parseDateToCET = (dateStr: string, isCheckIn = false, isCheckOut = false): string => {
      try {
        if (!dateStr) {
          return getCurrentDateWithOffset(isCheckIn, isCheckOut);
        }
        
        // Parse date string to Date object
        const date = new Date(dateStr);
        
        // Check if the date is valid
        if (isNaN(date.getTime())) {
          console.error("Invalid date:", dateStr);
          return getCurrentDateWithOffset(isCheckIn, isCheckOut);
        }
        
        // Add time component based on check-in/check-out status
        let adjustedDate = new Date(date);
        if (isCheckIn) {
          adjustedDate.setHours(15, 0, 0, 0); // 3:00 PM for check-in
        } else if (isCheckOut) {
          adjustedDate.setHours(10, 0, 0, 0); // 10:00 AM for check-out
        }
        
        // Format as ISO 8601 with CET timezone (+01:00)
        const isoDate = adjustedDate.toISOString().replace('Z', '+01:00');
        return isoDate;
      } catch (e) {
        console.error("Date parsing failed for:", dateStr, e);
        // Fallback to current date in ISO format with CET timezone
        return getCurrentDateWithOffset(isCheckIn, isCheckOut);
      }
    };
    
    // Helper function to get current date with proper offset and time
    const getCurrentDateWithOffset = (isCheckIn = false, isCheckOut = false): string => {
      const now = new Date();
      if (isCheckIn) {
        now.setHours(15, 0, 0, 0); // 3:00 PM
      } else if (isCheckOut) {
        // Set checkout to tomorrow at 10:00 AM if we're using fallback
        now.setDate(now.getDate() + 1);
        now.setHours(10, 0, 0, 0); // 10:00 AM
      }
      return now.toISOString().replace('Z', '+01:00');
    };
    
    // Determine hotel name with prioritized strategy
    let hotelNameValue: string;
    if (hotelInfo.hotelName) {
      // Priority 1: HTML anchor content
      hotelNameValue = hotelInfo.hotelName;
    } else if (hotelNameMatch && hotelNameMatch[1]?.trim()) {
      // Priority 2: Regex from body
      hotelNameValue = hotelNameMatch[1].trim();
    } else if (hotelNameFallbackMatch && hotelNameFallbackMatch[1]?.trim()) {
      // Priority 3: Fallback regex
      hotelNameValue = hotelNameFallbackMatch[1].trim();
    } else {
      // Priority 4: Default to "Unknown Hotel"
      hotelNameValue = 'Unknown Hotel';
    }
    
    // Determine hotel URL
    const hotelUrlValue = hotelInfo.hotelUrl || (hotelUrlMatch ? hotelUrlMatch[0] : null);
    
    // Set reasonable fallback for check-in (today) and check-out (tomorrow)
    const checkInDate = checkInMatch ? 
      parseDateToCET(checkInMatch[1], true, false) : 
      getCurrentDateWithOffset(true, false);
      
    const checkOutDate = checkOutMatch ? 
      parseDateToCET(checkOutMatch[1], false, true) : 
      getCurrentDateWithOffset(false, true);
    
    // For cancellation date, use the match if available, otherwise use check-in date
    const cancellationDate = cancellationMatch ? 
      parseDateToCET(cancellationMatch[1]) : 
      checkInDate; 

    // Parse the price - replace any comma with a period for consistency
    const priceValue = priceMatch ? 
      parseFloat(priceMatch[1].replace(',', '.')) : 
      0; // Use 0 as fallback

    // Get booking reference
    const bookingReference = bookingRefMatch ? bookingRefMatch[1] : `UNKNOWN-${Date.now()}`;

    // Extract cancellation policy
    const cancellationPolicy = cancellationPolicyMatch ? 
      `Free cancellation until ${cancellationPolicyMatch[1]}` : 
      null;

    console.log("Final extracted values:", {
      booking_reference: bookingReference,
      hotel_name: hotelNameValue,
      hotel_url: hotelUrlValue,
      price_paid: priceValue,
      room_type: roomTypeMatch ? roomTypeMatch[1].trim() : null
    });

    return {
      booking_reference: bookingReference,
      hotel_name: hotelNameValue,
      hotel_url: hotelUrlValue,
      price_paid: priceValue,
      room_type: roomTypeMatch ? roomTypeMatch[1].trim() : null,
      check_in_date: checkInDate,
      check_out_date: checkOutDate,
      cancellation_date: cancellationDate,
      email_id: emailId,
      currency: 'EUR', // Default to EUR for Booking.com
      cancellation_policy: cancellationPolicy || undefined,
      source: 'gmail',
      imported_from_gmail: true,
      import_timestamp: new Date().toISOString()
    };
  } catch (error) {
    console.error('Error extracting booking info:', error);
    // Return fallback data in case of error to avoid crashes
    return {
      booking_reference: `ERROR-${Date.now()}`,
      hotel_name: 'Error Processing Booking',
      hotel_url: null,
      price_paid: 0,
      room_type: null,
      check_in_date: new Date().toISOString().replace('Z', '+01:00'),
      check_out_date: new Date(new Date().setDate(new Date().getDate() + 1)).toISOString().replace('Z', '+01:00'),
      cancellation_date: new Date().toISOString().replace('Z', '+01:00'),
      email_id: emailId,
      currency: 'EUR',
      source: 'gmail',
      imported_from_gmail: true,
      import_timestamp: new Date().toISOString()
    };
  }
}

// Decode base64url to text
function base64UrlDecode(base64Url: string): string {
  // Convert base64url to base64
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  
  // Decode base64
  const binaryStr = atob(base64);
  
  // Convert binary string to UTF-8
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i);
  }
  
  return new TextDecoder().decode(bytes);
}

// Extract the content from a MIME message
function extractEmailContent(message: GmailMessage): { text: string, html: string | null } {
  const result = { text: '', html: null };
  
  // Helper to find parts by MIME type
  const findParts = (parts: any[], mimeType: string): string[] => {
    const contents: string[] = [];
    
    for (const part of parts) {
      if (part.mimeType === mimeType && part.body?.data) {
        contents.push(base64UrlDecode(part.body.data));
      }
      
      if (part.parts) {
        contents.push(...findParts(part.parts, mimeType));
      }
    }
    
    return contents;
  };
  
  // First, check for HTML parts
  if (message.payload.parts) {
    const htmlContents = findParts(message.payload.parts, 'text/html');
    if (htmlContents.length > 0) {
      result.html = htmlContents.join('\n');
    }
    
    const textContents = findParts(message.payload.parts, 'text/plain');
    if (textContents.length > 0) {
      result.text = textContents.join('\n');
    }
  }
  
  // If we have direct content in the payload
  if (!result.html && message.payload.mimeType === 'text/html' && message.payload.body?.data) {
    result.html = base64UrlDecode(message.payload.body.data);
  }
  
  if (!result.text && message.payload.mimeType === 'text/plain' && message.payload.body?.data) {
    result.text = base64UrlDecode(message.payload.body.data);
  }
  
  // If we still don't have text, use the snippet as a fallback
  if (!result.text && !result.html) {
    result.text = message.snippet || '';
  }
  
  return result;
}

// Process Gmail messages to extract booking information
async function processGmailMessages(accessToken: string, userId: string, parsingRules?: ParsingRules): Promise<BookingInfo[]> {
  try {
    // Build query based on parsing rules or use default
    let query = 'from:booking.com subject:"Your booking is confirmed"';
    
    if (parsingRules) {
      query = `from:${parsingRules.match.from} subject:"${parsingRules.match.subjectContains}"`;
    }
    
    console.log(`Searching Gmail with query: ${query}`);
    
    const response = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/messages?q=${encodeURIComponent(query)}`, 
      {
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
      }
    );

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Gmail API error: ${response.status} ${response.statusText} - ${errorText}`);
    }

    const data = await response.json();
    console.log(`Found ${data.messages?.length || 0} booking.com confirmation emails`);
    
    if (!data.messages || data.messages.length === 0) {
      console.log('No booking.com confirmation emails found');
      return [];
    }

    const bookings: BookingInfo[] = [];

    // Process each message (limit to 20 to avoid hitting rate limits)
    const messagesToProcess = data.messages.slice(0, 20);
    
    for (const messageInfo of messagesToProcess) {
      console.log(`Processing message ID: ${messageInfo.id}`);
      const messageResponse = await fetch(
        `https://gmail.googleapis.com/gmail/v1/users/me/messages/${messageInfo.id}?format=full`, 
        {
          headers: {
            'Authorization': `Bearer ${accessToken}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!messageResponse.ok) {
        console.error(`Error fetching message ${messageInfo.id}: ${messageResponse.status}`);
        continue;
      }

      const message: GmailMessage = await messageResponse.json();
      
      // Get the subject line
      const subjectHeader = message.payload.headers.find(h => h.name.toLowerCase() === 'subject');
      const subject = subjectHeader?.value || '';
      
      // Check if this is truly a booking confirmation
      const subjectMatch = parsingRules ? 
        subject.includes(parsingRules.match.subjectContains) : 
        subject.includes('Your booking is confirmed');
        
      if (!subjectMatch) {
        console.log(`Skipping message ID ${messageInfo.id}: Not a booking confirmation`);
        continue;
      }
      
      // Extract the content from the email
      const emailContent = extractEmailContent(message);
      
      // Prefer HTML content for extraction if available
      const contentToProcess = emailContent.html || emailContent.text;
      
      // Extract booking information from the email content using parsing rules
      const bookingInfo = extractBookingInfo(contentToProcess, message.id, parsingRules);
      
      if (bookingInfo) {
        console.log(`Successfully extracted booking info for ${bookingInfo.hotel_name}`);
        bookings.push(bookingInfo);
        
        // Save the booking to the user's bookings in the database using upsert
        const { error } = await supabase
          .from('bookings')
          .upsert(
            { 
              user_id: userId,
              booking_reference: bookingInfo.booking_reference,
              hotel_name: bookingInfo.hotel_name,
              hotel_url: bookingInfo.hotel_url,
              price_paid: bookingInfo.price_paid,
              room_type: bookingInfo.room_type,
              check_in_date: bookingInfo.check_in_date,
              check_out_date: bookingInfo.check_out_date,
              cancellation_date: bookingInfo.cancellation_date,
              email_id: bookingInfo.email_id,
              currency: bookingInfo.currency,
              cancellation_policy: bookingInfo.cancellation_policy,
              source: bookingInfo.source,
              imported_from_gmail: bookingInfo.imported_from_gmail,
              import_timestamp: bookingInfo.import_timestamp,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
            { 
              onConflict: 'booking_reference',
              ignoreDuplicates: false // Update if exists
            }
          );
        
        if (error) {
          console.error('Error saving booking to database:', error);
        } else {
          console.log(`Saved booking for ${bookingInfo.hotel_name} to database (confirmation #${bookingInfo.booking_reference})`);
        }
      } else {
        console.log(`Could not extract booking info from message ID ${messageInfo.id}`);
      }
    }

    return bookings;
  } catch (error) {
    console.error('Error processing Gmail messages:', error);
    throw error;
  }
}

serve(async (req) => {
  // Handle CORS preflight request
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders, status: 204 });
  }

  try {
    if (req.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), { 
        status: 405,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    const { accessToken, userId, parsingRules } = await req.json();

    if (!accessToken || !userId) {
      return new Response(JSON.stringify({ error: 'Missing required parameters' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    console.log(`Processing Gmail messages for user ${userId}`);
    const bookings = await processGmailMessages(accessToken, userId, parsingRules);

    return new Response(JSON.stringify({ success: true, bookings }), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  } catch (error) {
    console.error('Error in process-gmail function:', error);
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' }
    });
  }
});
