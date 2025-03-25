
import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { 
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger 
} from '@/components/ui/dropdown-menu';
import { ChevronDown, RefreshCw, Check, AlertCircle, Wrench } from 'lucide-react';
import { supabase } from '@/integrations/supabase/client';

interface FetchBookingsButtonProps {
  onFetchComplete: () => void;
}

const FetchBookingsButton = ({ onFetchComplete }: FetchBookingsButtonProps) => {
  const [isLoading, setIsLoading] = useState(false);
  const [action, setAction] = useState<string>('');

  const handleFetchBookings = async (option?: string) => {
    setIsLoading(true);
    setAction(option || 'Fetching prices');
    
    try {
      let endpoint = '/functions/fetch-hotel-prices';
      let params = {};
      
      switch(option) {
        case 'test-auth':
          params = { testAuth: true };
          break;
        case 'check-urls':
          params = { checkUrlIntegrity: true };
          break;
        case 'fetch-single':
          // Get the first booking id
          const { data: bookings, error: bookingError } = await supabase
            .from('bookings')
            .select('id')
            .limit(1);
            
          if (bookingError || !bookings || bookings.length === 0) {
            throw new Error('No bookings found to test with');
          }
          
          params = { bookingId: bookings[0].id };
          break;
        default:
          params = { processAll: true };
      }
      
      // Convert params to query string
      const queryString = Object.entries(params)
        .map(([key, value]) => `${key}=${value}`)
        .join('&');
        
      // Trigger the edge function with params
      console.log(`Calling edge function: ${endpoint}?${queryString}`);
      const response = await fetch(`${endpoint}?${queryString}`);
      
      // Check for HTML response (error case)
      const contentType = response.headers.get('content-type');
      if (contentType && contentType.includes('text/html')) {
        console.error('Received HTML response instead of JSON');
        throw new Error('Received HTML instead of JSON. The server might be returning an error page.');
      }
      
      if (!response.ok) {
        console.error(`HTTP error: ${response.status} ${response.statusText}`);
        throw new Error(`HTTP error: ${response.status} ${response.statusText}`);
      }
      
      // Handle the response
      let data;
      try {
        data = await response.json();
      } catch (parseError) {
        console.error('JSON parsing error:', parseError);
        console.error('Response text:', await response.text());
        throw new Error('Failed to parse response as JSON. Check console for details.');
      }

      if (data.success) {
        if (option === 'test-auth') {
          if (data.authTest?.success) {
            toast.success('Authentication test successful!');
          } else {
            toast.error('Authentication test failed. Check edge function logs.');
          }
        } else if (option === 'check-urls') {
          const integrity = data.urlIntegrity;
          if (integrity.invalid > 0) {
            toast.warning(`Found ${integrity.invalid} invalid hotel URLs out of ${integrity.valid + integrity.invalid} total.`);
          } else {
            toast.success(`All ${integrity.valid} hotel URLs are valid.`);
          }
        } else if (option === 'fetch-single') {
          toast.success('Single booking fetch completed. Check logs for details.');
        } else {
          toast.success('Bookings fetched successfully!');
        }
        
        onFetchComplete(); // Refresh bookings in the dashboard
      } else {
        toast.error(`Failed: ${data.error || 'Unknown error'}`);
      }
    } catch (error: any) {
      console.error('Error:', error);
      toast.error(`Failed to execute operation: ${error.message}`);
    } finally {
      setIsLoading(false);
      setAction('');
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button disabled={isLoading} className="flex items-center gap-1">
          {isLoading ? (
            <>
              <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
              {action}...
            </>
          ) : (
            <>
              Fetch Prices
              <ChevronDown className="h-4 w-4 ml-1" />
            </>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => handleFetchBookings()}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Fetch All Prices
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => handleFetchBookings('check-urls')}>
          <Check className="h-4 w-4 mr-2" />
          Check URL Integrity
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => handleFetchBookings('test-auth')}>
          <AlertCircle className="h-4 w-4 mr-2" />
          Test Authentication
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => handleFetchBookings('fetch-single')}>
          <Wrench className="h-4 w-4 mr-2" />
          Test Single Booking
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default FetchBookingsButton;
