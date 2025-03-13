
import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Inbox, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';

interface FetchBookingsButtonProps {
  onFetchComplete?: () => void;
}

const FetchBookingsButton: React.FC<FetchBookingsButtonProps> = ({ onFetchComplete }) => {
  const [isFetching, setIsFetching] = useState(false);
  const { user, isGmailConnected } = useAuth();

  const handleFetchBookings = async () => {
    if (!isGmailConnected || !user) {
      toast.error('Gmail not connected. Please connect Gmail in your profile.');
      return;
    }

    try {
      setIsFetching(true);
      
      // Get the current session for the access token
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session?.provider_token) {
        toast.error('Unable to access Gmail. Please reconnect your account.');
        return;
      }
      
      // Call our edge function to process Gmail messages with the updated parsing rules
      const { data, error } = await supabase.functions.invoke('process-gmail', {
        body: {
          accessToken: session.provider_token,
          userId: user.id,
          parsingRules: {
            match: {
              from: "noreply@booking.com",
              subjectContains: "Thanks! Your booking is confirmed"
            },
            extract: {
              confirmation_number: "regex:Confirmation:\\s*(\\d+)",
              hotel_name: "regex:Thanks, .*? Your booking in .*? is\\s*confirmed\\.\\s*(.*?)\\s*is expecting you",
              hotel_url: "regex:https:\\/\\/www\\.booking\\.com\\/hotel\\/[^\\s]+",
              price_paid: "regex:Total Price\\s*€\\s*(\\d+\\.\\d{2})",
              room_type: "regex:Your reservation.*?\\n.*?,\\s*(.*?)\\n",
              check_in_date: "regex:Check-in\\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\\s*(\\w+ \\d{1,2}, \\d{4})",
              check_out_date: "regex:Check-out\\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\\s*(\\w+ \\d{1,2}, \\d{4})",
              cancellation_date: "regex:cancel for FREE until\\s*(\\w+ \\d{1,2}, \\d{4} \\d{2}:\\d{2} [AP]M)"
            }
          }
        }
      });
      
      if (error) {
        throw new Error(error.message);
      }
      
      const newBookings = data?.bookings?.length || 0;
      
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
      
      // Notify parent component that fetch is complete
      if (onFetchComplete) {
        onFetchComplete();
      }
      
    } catch (error: any) {
      console.error('Error fetching bookings from Gmail:', error);
      toast.error(error.message || 'Error fetching bookings');
    } finally {
      setIsFetching(false);
    }
  };

  return (
    <Button 
      onClick={handleFetchBookings}
      variant="outline"
      disabled={isFetching || !isGmailConnected}
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
