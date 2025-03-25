
import React from 'react';
import { Button } from '@/components/ui/button';
import { ExternalLink } from 'lucide-react';
import { format, isValid, parse } from 'date-fns';

interface RebookHotelButtonProps {
  hotelName: string;
  cheaperPrice: boolean;
  checkInDate?: string;
  checkOutDate?: string;
  groupAdults?: number;
}

/**
 * Creates a properly formatted booking.com URL with necessary parameters
 */
export const createBookingUrl = (
  hotelName: string, 
  checkIn?: string, 
  checkOut?: string, 
  groupAdults?: number
): string => {
  // Validate required parameters
  if (!checkIn || !checkOut || !groupAdults) {
    throw new Error('Missing required booking parameters');
  }

  const encodedHotelName = encodeURIComponent(hotelName);
  
  // Extract the base URL and format it properly
  // First check if it contains 'hotel/' to determine if it's a specific hotel URL
  let url: string;
  if (hotelName.includes('/')) {
    // If it already appears to be a URL, ensure proper encoding and protocol
    if (!hotelName.startsWith('http://') && !hotelName.startsWith('https://')) {
      url = `https://${hotelName}`;
    } else {
      url = hotelName;
    }
    
    // Validate the URL is properly formed
    try {
      new URL(url);
    } catch (e) {
      // If invalid URL, fall back to search
      url = `https://www.booking.com/searchresults.html?ss=${encodedHotelName}`;
    }
  } else {
    // Otherwise create a search URL with the hotel name
    url = `https://www.booking.com/searchresults.html?ss=${encodedHotelName}`;
  }

  // Format dates for booking.com (YYYY-MM-DD)
  const formatDateForBooking = (dateString: string): string => {
    try {
      const date = new Date(dateString);
      
      if (!isValid(date)) {
        throw new Error(`Invalid date: ${dateString}`);
      }
      
      return format(date, 'yyyy-MM-dd');
    } catch (error) {
      console.error('Error formatting date:', error);
      throw new Error('Missing required booking parameters');
    }
  };
  
  try {
    // Create a URL object for proper parameter handling
    const urlObj = new URL(url);
    
    // Add parameters to URL
    urlObj.searchParams.set('checkin', formatDateForBooking(checkIn));
    urlObj.searchParams.set('checkout', formatDateForBooking(checkOut));
    urlObj.searchParams.set('group_adults', groupAdults.toString());
    
    // Generate the final URL
    const finalUrl = urlObj.toString();
    console.log(`Generated booking URL: ${finalUrl}`);
    
    return finalUrl;
  } catch (error) {
    console.error('Error creating URL object:', error);
    
    // Fallback to manual string concatenation
    const params = new URLSearchParams();
    params.append('checkin', formatDateForBooking(checkIn));
    params.append('checkout', formatDateForBooking(checkOut));
    params.append('group_adults', groupAdults.toString());
    
    // Add parameters to the URL
    return `${url}${url.includes('?') ? '&' : '?'}${params.toString()}`;
  }
};

const RebookHotelButton = ({ 
  hotelName, 
  cheaperPrice, 
  checkInDate, 
  checkOutDate,
  groupAdults = 2 // Default to 2 adults if not specified
}: RebookHotelButtonProps) => {
  // Only render the button if the current price is cheaper
  if (!cheaperPrice) {
    return null;
  }

  const handleRebook = () => {
    try {
      const bookingUrl = createBookingUrl(hotelName, checkInDate, checkOutDate, groupAdults);
      window.open(bookingUrl, '_blank');
    } catch (error) {
      console.error('Error creating booking URL:', error);
      // You could show a toast here to inform the user
    }
  };

  return (
    <Button 
      size="sm"
      className="flex items-center gap-1.5"
      onClick={handleRebook}
    >
      <span>Rebook</span>
      <ExternalLink className="h-3.5 w-3.5" />
    </Button>
  );
};

export default RebookHotelButton;
