
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
}

// Extract booking information from email content using the provided parsing rules
function extractBookingInfo(body: string, emailId: string, parsingRules?: ParsingRules): BookingInfo | null {
  try {
    console.log("Extracting booking info from email");
    
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
      
      // Enhanced hotel URL extraction with "linkContains:/hotel/" pattern
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
      priceRegex = /Total Price\s*€\s*(\d+\.\d{2})/i;
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
    const hotelUrlMatch = body.match(hotelUrlRegex);

    // Extract hotel name from URL if needed
    let hotelNameFromUrl = "";
    if (hotelUrlMatch) {
      const urlPath = hotelUrlMatch[0].split('/hotel/')[1];
      if (urlPath) {
        // Get the last part of the URL path which is usually the hotel slug
        const hotelSlug = urlPath.split('/').pop() || urlPath.split('/')[1] || "";
        // Convert slug to readable name (replace hyphens with spaces and capitalize)
        hotelNameFromUrl = hotelSlug
          .split('-')
          .map(word => word.charAt(0).toUpperCase() + word.slice(1))
          .join(' ');
      }
    }

    console.log("Regex matches:", {
      bookingRef: bookingRefMatch?.[1] || 'Not found',
      hotelName: hotelNameMatch?.[1] || 'Not found',
      hotelNameFallback: hotelNameFallbackMatch?.[1] || 'Not found',
      hotelNameFromUrl: hotelNameFromUrl || 'Not found',
      roomType: roomTypeMatch?.[1] || 'Not found',
      checkIn: checkInMatch?.[1] || 'Not found',
      checkOut: checkOutMatch?.[1] || 'Not found',
      cancellation: cancellationMatch?.[1] || 'Not found',
      price: priceMatch?.[1] || 'Not found',
      hotelUrl: hotelUrlMatch?.[0] || 'Not found'
    });

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
    
    // Determine hotel name with fallback strategy
    let hotelNameValue: string;
    if (hotelNameMatch && hotelNameMatch[1]?.trim()) {
      hotelNameValue = hotelNameMatch[1].trim();
    } else if (hotelNameFallbackMatch && hotelNameFallbackMatch[1]?.trim()) {
      hotelNameValue = hotelNameFallbackMatch[1].trim();
    } else if (hotelNameFromUrl) {
      hotelNameValue = hotelNameFromUrl;
    } else {
      hotelNameValue = 'Unknown Hotel';
    }
    
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

    return {
      booking_reference: bookingRefMatch ? bookingRefMatch[1] : 'UNKNOWN-' + Date.now(),
      hotel_name: hotelNameValue,
      hotel_url: hotelUrlMatch ? hotelUrlMatch[0] : null, // Using [0] for the full match
      price_paid: priceValue,
      room_type: roomTypeMatch ? roomTypeMatch[1].trim() : null,
      check_in_date: checkInDate,
      check_out_date: checkOutDate,
      cancellation_date: cancellationDate,
      email_id: emailId
    };
  } catch (error) {
    console.error('Error extracting booking info:', error);
    // Return fallback data in case of error to avoid crashes
    return {
      booking_reference: 'ERROR-' + Date.now(),
      hotel_name: 'Error Processing Booking',
      hotel_url: null,
      price_paid: 0,
      room_type: null,
      check_in_date: new Date().toISOString().replace('Z', '+01:00'),
      check_out_date: new Date(new Date().setDate(new Date().getDate() + 1)).toISOString().replace('Z', '+01:00'),
      cancellation_date: new Date().toISOString().replace('Z', '+01:00'),
      email_id: emailId
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

// Extract the plain text from a MIME message
function extractPlainText(message: GmailMessage): string {
  // Try to find plain text part
  const findPlainTextPart = (parts: any[]): string | null => {
    for (const part of parts) {
      if (part.mimeType === 'text/plain' && part.body?.data) {
        return base64UrlDecode(part.body.data);
      } else if (part.parts) {
        const text = findPlainTextPart(part.parts);
        if (text) return text;
      }
    }
    return null;
  };

  // First, check if the message has parts
  if (message.payload.parts) {
    const text = findPlainTextPart(message.payload.parts);
    if (text) return text;
  }

  // If no plain text was found in parts, try the body directly
  if (message.payload.mimeType === 'text/plain' && message.payload.body?.data) {
    return base64UrlDecode(message.payload.body.data);
  }

  // If we still don't have text, use the snippet as a fallback
  return message.snippet || '';
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
      
      // Extract the plain text content from the email
      const emailContent = extractPlainText(message);
      
      // Extract booking information from the email content using parsing rules
      const bookingInfo = extractBookingInfo(emailContent, message.id, parsingRules);
      
      if (bookingInfo) {
        console.log(`Successfully extracted booking info for ${bookingInfo.hotel_name}`);
        bookings.push(bookingInfo);
        
        // Save the booking to the user's bookings in the database
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
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            },
            { onConflict: 'email_id' }
          );
        
        if (error) {
          console.error('Error saving booking to database:', error);
        } else {
          console.log(`Saved booking for ${bookingInfo.hotel_name} to database`);
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
