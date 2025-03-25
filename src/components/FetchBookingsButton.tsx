import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';

interface FetchBookingsButtonProps {
  onFetchComplete: () => void;
}

const FetchBookingsButton = ({ onFetchComplete }: FetchBookingsButtonProps) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleFetchBookings = async () => {
    setIsLoading(true);
    try {
      // Trigger the edge function to fetch bookings
      const response = await fetch('/functions/fetch-hotel-prices?processAll=true');
      const data = await response.json();

      if (data.success) {
        toast.success('Bookings fetched successfully!');
        onFetchComplete(); // Refresh bookings in the dashboard
      } else {
        toast.error(`Failed to fetch bookings: ${data.error || 'Unknown error'}`);
      }
    } catch (error: any) {
      console.error('Error fetching bookings:', error);
      toast.error('Failed to fetch bookings. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Button onClick={handleFetchBookings} disabled={isLoading}>
      {isLoading ? 'Fetching...' : 'Fetch Prices'}
    </Button>
  );
};

export default FetchBookingsButton;
