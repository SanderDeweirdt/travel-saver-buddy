
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

interface BookingInfo {
  hotel_name: string;
  check_in_date: string;
  check_out_date: string;
  price_paid: number;
  booking_reference: string;
  email_id: string;
}

// Extract booking information from email content
function extractBookingInfo(body: string, emailId: string): BookingInfo | null {
  try {
    // Simple regex patterns to match booking information
    // In a real-world application, these patterns would be more sophisticated
    // and tailored to the specific format of booking.com emails
    const hotelNameRegex = /Hotel name:\s*(.*?)(?=\n|$)/i;
    const checkInRegex = /Check-in:\s*(\d{1,2} [a-zA-Z]+ \d{4})/i;
    const checkOutRegex = /Check-out:\s*(\d{1,2} [a-zA-Z]+ \d{4})/i;
    const priceRegex = /Total price:\s*[\$€£]?(\d+[\.,]\d{2})/i;
    const bookingRefRegex = /Booking reference:\s*([A-Z0-9]+)/i;

    // Match the patterns in the email body
    const hotelNameMatch = body.match(hotelNameRegex);
    const checkInMatch = body.match(checkInRegex);
    const checkOutMatch = body.match(checkOutRegex);
    const priceMatch = body.match(priceRegex);
    const bookingRefMatch = body.match(bookingRefRegex);

    // If we couldn't match the essential info, return null
    if (!hotelNameMatch || !checkInMatch || !checkOutMatch || !priceMatch) {
      console.log("Couldn't extract necessary booking info from email");
      return null;
    }

    // Parse the dates
    const checkInDate = new Date(checkInMatch[1]);
    const checkOutDate = new Date(checkOutMatch[1]);

    // Parse the price - replace any comma with a period for consistency
    const price = parseFloat(priceMatch[1].replace(',', '.'));

    return {
      hotel_name: hotelNameMatch[1].trim(),
      check_in_date: checkInDate.toISOString(),
      check_out_date: checkOutDate.toISOString(),
      price_paid: price,
      booking_reference: bookingRefMatch ? bookingRefMatch[1] : 'UNKNOWN',
      email_id: emailId
    };
  } catch (error) {
    console.error('Error extracting booking info:', error);
    return null;
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
async function processGmailMessages(accessToken: string, userId: string): Promise<BookingInfo[]> {
  try {
    // Search for booking.com confirmation emails
    const query = 'from:booking.com subject:(confirmation)';
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
      throw new Error(`Gmail API error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    if (!data.messages || data.messages.length === 0) {
      console.log('No booking.com confirmation emails found');
      return [];
    }

    const bookings: BookingInfo[] = [];

    // Process each message (limit to 10 to avoid hitting rate limits)
    const messagesToProcess = data.messages.slice(0, 10);
    
    for (const messageInfo of messagesToProcess) {
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
      
      // Extract the plain text content from the email
      const emailContent = extractPlainText(message);
      
      // Extract booking information from the email content
      const bookingInfo = extractBookingInfo(emailContent, message.id);
      
      if (bookingInfo) {
        bookings.push(bookingInfo);
        
        // Save the booking to the user's bookings in the database
        const { error } = await supabase
          .from('bookings')
          .upsert(
            { 
              user_id: userId,
              hotel_name: bookingInfo.hotel_name,
              check_in_date: bookingInfo.check_in_date,
              check_out_date: bookingInfo.check_out_date,
              price_paid: bookingInfo.price_paid,
              booking_reference: bookingInfo.booking_reference,
              email_id: bookingInfo.email_id,
              created_at: new Date().toISOString(),
            },
            { onConflict: 'email_id' }
          );
        
        if (error) {
          console.error('Error saving booking to database:', error);
        } else {
          console.log(`Saved booking for ${bookingInfo.hotel_name}`);
        }
      }
    }

    return bookings;
  } catch (error) {
    console.error('Error processing Gmail messages:', error);
    return [];
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

    const { accessToken, userId } = await req.json();

    if (!accessToken || !userId) {
      return new Response(JSON.stringify({ error: 'Missing required parameters' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }
      });
    }

    const bookings = await processGmailMessages(accessToken, userId);

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
