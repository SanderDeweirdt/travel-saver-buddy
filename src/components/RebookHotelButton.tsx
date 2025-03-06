
import React from 'react';
import { Button } from '@/components/ui/button';
import { ExternalLink } from 'lucide-react';

interface RebookHotelButtonProps {
  hotelName: string;
  cheaperPrice: boolean;
}

const RebookHotelButton = ({ hotelName, cheaperPrice }: RebookHotelButtonProps) => {
  // Only render the button if the current price is cheaper
  if (!cheaperPrice) {
    return null;
  }

  // Create the booking.com search URL with the hotel name as a parameter
  const createBookingUrl = (hotelName: string) => {
    const encodedHotelName = encodeURIComponent(hotelName);
    return `https://www.booking.com/searchresults.html?ss=${encodedHotelName}`;
  };

  return (
    <Button 
      size="sm"
      className="flex items-center gap-1.5"
      onClick={() => window.open(createBookingUrl(hotelName), '_blank')}
    >
      <span>Rebook</span>
      <ExternalLink className="h-3.5 w-3.5" />
    </Button>
  );
};

export default RebookHotelButton;
