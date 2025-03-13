
import React from 'react';
import { Button } from '@/components/ui/button';
import { ExternalLink } from 'lucide-react';

interface RebookHotelButtonProps {
  hotelName: string;
  cheaperPrice: boolean;
  checkInDate?: string;
  checkOutDate?: string;
}

const RebookHotelButton = ({ 
  hotelName, 
  cheaperPrice, 
  checkInDate, 
  checkOutDate 
}: RebookHotelButtonProps) => {
  // Only render the button if the current price is cheaper
  if (!cheaperPrice) {
    return null;
  }

  // Create the booking.com search URL with the hotel name and dates as parameters
  const createBookingUrl = (hotelName: string, checkIn?: string, checkOut?: string) => {
    const encodedHotelName = encodeURIComponent(hotelName);
    let url = `https://www.booking.com/searchresults.html?ss=${encodedHotelName}`;
    
    // Add check-in and check-out dates if provided
    if (checkIn && checkOut) {
      // Format dates for booking.com (YYYY-MM-DD)
      const formatDate = (dateString: string) => {
        const date = new Date(dateString);
        return date.toISOString().split('T')[0];
      };
      
      try {
        const formattedCheckIn = formatDate(checkIn);
        const formattedCheckOut = formatDate(checkOut);
        
        url += `&checkin=${formattedCheckIn}&checkout=${formattedCheckOut}`;
      } catch (error) {
        console.error('Error formatting dates:', error);
        // Continue without dates if there's an error
      }
    }
    
    return url;
  };

  return (
    <Button 
      size="sm"
      className="flex items-center gap-1.5"
      onClick={() => window.open(createBookingUrl(hotelName, checkInDate, checkOutDate), '_blank')}
    >
      <span>Rebook</span>
      <ExternalLink className="h-3.5 w-3.5" />
    </Button>
  );
};

export default RebookHotelButton;
