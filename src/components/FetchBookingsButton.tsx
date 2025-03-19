
import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Inbox, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth, GMAIL_API_SCOPES } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';

/**
 * Function to check if a Gmail account is connected
 * @param user The user object from auth context
 * @returns Boolean indicating if Gmail is connected
 */
const isGmailAccountConnected = (user: any): boolean => {
  if (!user) return false;
  
  // Check if user has an email (basic validation)
  if (!user.email) {
    console.warn('User context missing email property');
    return false;
  }
  
  // Check if the user has explicitly connected Gmail
  return user.user_metadata?.gmail_connected === true;
};

interface FetchBookingsButtonProps {
  onFetchComplete?: () => void;
}

const FetchBookingsButton: React.FC<FetchBookingsButtonProps> = ({ onFetchComplete }) => {
  const [isFetching, setIsFetching] = useState(false);
  const { user, isGmailConnected, connectGmail } = useAuth();
  const [retryCount, setRetryCount] = useState(0);
  const MAX_RETRIES = 3;
  
  // Use our dedicated function to check Gmail connection
  const gmailConnected = isGmailAccountConnected(user);

  const handleFetchBookings = async () => {
    if (!gmailConnected || !user) {
      toast.error('Gmail not connected. Please connect Gmail in your profile.');
      return;
    }

    try {
      setIsFetching(true);
      
      // Get the current session for the access token
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session?.provider_token) {
        console.error('No provider token available');
        toast.error('Unable to access Gmail. Please reconnect your account.');
        await reconnectGmail();
        return;
      }
      
      // Call our edge function to process Gmail messages with the enhanced parsing rules
      const response = await processGmailWithRetry(session.provider_token, user.id);
      
      if (response.error) {
        throw new Error(response.error);
      }
      
      const newBookings = response.data?.bookings?.length || 0;
      
      if (newBookings > 0) {
        toast.success(`Imported ${newBookings} bookings from your Gmail`);
      } else {
        toast.info('No new Booking.com confirmations found in your Gmail');
      }
      
      // Store the last import date in user metadata
      await supabase.auth.updateUser({
        data: { 
          last_gmail_import: new Date().toISOString(),
          gmail_imported_bookings: (user.user_metadata?.gmail_imported_bookings || 0) + newBookings
        }
      });
      
      // Reset retry count on successful operation
      setRetryCount(0);
      
      // Notify parent component that fetch is complete
      if (onFetchComplete) {
        onFetchComplete();
      }
      
    } catch (error: any) {
      console.error('Error fetching bookings from Gmail:', error);
      
      if (error.message?.includes('reconnect') || error.message?.includes('token')) {
        await reconnectGmail();
      }
      
      toast.error(error.message || 'Error fetching bookings');
    } finally {
      setIsFetching(false);
    }
  };

  const reconnectGmail = async () => {
    toast.info('Reconnecting to Gmail...');
    try {
      await connectGmail();
      toast.success('Gmail reconnected. Please try fetching bookings again.');
    } catch (error) {
      console.error('Failed to reconnect Gmail:', error);
      toast.error('Failed to reconnect Gmail. Please try again later.');
    }
  };

  const processGmailWithRetry = async (accessToken: string, userId: string, currentRetry = 0): Promise<any> => {
    try {
      console.log(`Attempt ${currentRetry + 1}/${MAX_RETRIES + 1} to process Gmail`);
      
      const { data, error } = await supabase.functions.invoke('process-gmail', {
        body: {
          accessToken,
          userId,
          parsingRules: {
            match: {
              from: "noreply@booking.com",
              subjectContains: "Your booking is confirmed"
            },
            extract: {
              confirmation_number: "regex:Confirmation:\\s*(\\d+)",
              hotel_name: "regex:Your booking is confirmed at\\s*(.*)",
              hotel_url: "linkContains:/hotel/",
              price_paid: "regex:Total price<\\/div>\\s*<div><span>€\\s*(\\d+\\.\\d{2})<\\/span>",
              room_type: "regex:Your reservation<\\/strong><\\/div>\\s*<div>\\d+ night[s]*, ([^<]+)",
              check_in_date_raw: "regex:Check-in\\s*\\w+,\\s*(\\w+ \\d{1,2}, \\d{4})",
              check_out_date_raw: "regex:Check-out\\s*\\w+,\\s*(\\w+ \\d{1,2}, \\d{4})",
              cancellation_date_raw: "regex:cancel for FREE until\\s*(\\w+ \\d{1,2}, \\d{4} \\d{2}:\\d{2} [AP]M)"
            }
          }
        }
      });

      if (error) {
        console.error(`Gmail API error (attempt ${currentRetry + 1}):`, error);
        
        // Check if the error is related to authentication
        if ((error.message?.includes('403') || 
             error.message?.includes('401') || 
             error.message?.includes('authentication')) && 
            currentRetry < MAX_RETRIES) {
            
          console.log(`Token issue detected, attempt ${currentRetry + 1}/${MAX_RETRIES}. Refreshing token...`);
          
          // Refresh token by reconnecting to Gmail
          await connectGmail();
          
          // Wait a moment for the token to be refreshed
          await new Promise(resolve => setTimeout(resolve, 1000));
          
          // Get updated session
          const { data: { session: refreshedSession } } = await supabase.auth.getSession();
          
          if (!refreshedSession?.provider_token) {
            throw new Error('Failed to refresh token. Please try reconnecting your Gmail account.');
          }
          
          console.log('Token refreshed, retrying with new token');
          
          // Retry with new token
          return processGmailWithRetry(refreshedSession.provider_token, userId, currentRetry + 1);
        }
        
        throw error;
      }
      
      return { data, error: null };
      
    } catch (error: any) {
      console.error(`Error in Gmail API call (attempt ${currentRetry + 1}):`, error);
      
      // If we've reached max retries, give up
      if (currentRetry >= MAX_RETRIES) {
        return { 
          data: null, 
          error: `Gmail API error: ${error instanceof Error ? error.message : 'Unknown error'}. Please reconnect your Gmail account.` 
        };
      }
      
      // Otherwise retry
      console.log(`Error in Gmail API call, attempt ${currentRetry + 1}/${MAX_RETRIES}. Retrying...`);
      
      // Wait with exponential backoff before retrying
      const backoffTime = Math.pow(2, currentRetry) * 1000;
      await new Promise(resolve => setTimeout(resolve, backoffTime));
      
      return processGmailWithRetry(accessToken, userId, currentRetry + 1);
    }
  };

  return (
    <Button 
      onClick={handleFetchBookings}
      variant="outline"
      disabled={isFetching || !gmailConnected}
      className="flex items-center gap-2"
    >
      {isFetching ? (
        <>
          <Loader2 className="h-4 w-4 animate-spin" />
          Fetching bookings...
        </>
      ) : (
        <>
          <Inbox className="h-4 w-4" />
          Fetch New Bookings
        </>
      )}
    </Button>
  );
};

export default FetchBookingsButton;
