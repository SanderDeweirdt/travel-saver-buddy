
import React, { useState } from 'react';
import { format } from 'date-fns';
import { MoreHorizontal, RefreshCw, Trash, Edit, Loader2, AlertCircle } from 'lucide-react';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { 
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger 
} from '@/components/ui/tooltip';
import RebookHotelButton from './RebookHotelButton';
import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';

interface Booking {
  id: string;
  hotel_name: string;
  hotel_url: string | null;
  price_paid: number;
  room_type: string | null;
  check_in_date: string;
  check_out_date: string;
  fetched_price: number | null;
  fetched_price_updated_at: string | null;
  isLoading?: boolean;
  fetchError?: string;
}

interface BookingListViewProps {
  bookings: Booking[];
  onUpdate: (id: string) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

const BookingListView: React.FC<BookingListViewProps> = ({ 
  bookings, 
  onUpdate, 
  onDelete,
  onRefresh
}) => {
  const [loadingBookings, setLoadingBookings] = useState<Record<string, boolean>>({});
  const [isSyncingAll, setIsSyncingAll] = useState(false);
  const [isCheckingUrls, setIsCheckingUrls] = useState(false);

  // Format date string to a readable format
  const formatDate = (dateString: string) => {
    if (!dateString) return 'N/A';
    return format(new Date(dateString), 'MMM d, yyyy');
  };

  // Format price with two decimal places, safely handling null/undefined values
  const formatPrice = (price: number | null | undefined): string => {
    if (price === null || price === undefined) return 'N/A';
    return price.toFixed(2);
  };

  const handleSyncBooking = async (id: string) => {
    // Set loading state for this specific booking
    setLoadingBookings(prev => ({ ...prev, [id]: true }));
    
    try {
      // Call the edge function to fetch the price
      const response = await supabase.functions.invoke('fetch-hotel-prices', {
        body: { bookingId: id }
      });
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'Failed to sync booking');
      }
      
      toast.success(response.data.message || 'Price updated successfully');
      onRefresh(); // Refresh the booking list
    } catch (error: any) {
      toast.error(`Failed to sync: ${error.message}`);
    } finally {
      setLoadingBookings(prev => ({ ...prev, [id]: false }));
    }
  };

  const handleSyncAll = async () => {
    setIsSyncingAll(true);
    try {
      // Call the edge function to process all bookings
      const response = await supabase.functions.invoke('fetch-hotel-prices', {
        body: { processAll: true }
      });
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'Failed to sync all bookings');
      }
      
      onRefresh(); // Refresh all bookings
      
      // Show more detailed message
      const result = response.data.result;
      toast.success(`Processed ${result.total} bookings, ${result.successful} updated successfully`);
      
      // If there are invalid URLs, show a warning
      if (result.urlIntegrity && result.urlIntegrity.invalid > 0) {
        toast.warning(`Found ${result.urlIntegrity.invalid} invalid hotel URLs. Some bookings may not sync correctly.`);
      }
    } catch (error: any) {
      toast.error(`Failed to sync all bookings: ${error.message}`);
    } finally {
      setIsSyncingAll(false);
    }
  };

  const handleCheckUrlIntegrity = async () => {
    setIsCheckingUrls(true);
    try {
      // Call the edge function to check URL integrity
      const response = await supabase.functions.invoke('fetch-hotel-prices', {
        body: { checkUrlIntegrity: true }
      });
      
      if (!response.data.success) {
        throw new Error(response.data.error || 'Failed to check URL integrity');
      }
      
      const integrity = response.data.urlIntegrity;
      
      if (integrity.invalid > 0) {
        toast.warning(`Found ${integrity.invalid} invalid hotel URLs out of ${integrity.valid + integrity.invalid} total.`);
      } else {
        toast.success(`All ${integrity.valid} hotel URLs are valid.`);
      }
    } catch (error: any) {
      toast.error(`Failed to check URL integrity: ${error.message}`);
    } finally {
      setIsCheckingUrls(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Your Bookings</h2>
        <div className="flex gap-2">
          <Button 
            onClick={handleCheckUrlIntegrity}
            variant="outline"
            disabled={isCheckingUrls}
            size="sm"
          >
            {isCheckingUrls ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Checking URLs...
              </>
            ) : (
              <>
                <AlertCircle className="h-4 w-4 mr-2" />
                Verify URLs
              </>
            )}
          </Button>
          <Button 
            onClick={handleSyncAll}
            variant="outline"
            disabled={isSyncingAll}
          >
            {isSyncingAll ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Syncing...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4 mr-2" />
                Check prices
              </>
            )}
          </Button>
        </div>
      </div>
      
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Hotel</TableHead>
              <TableHead>Dates</TableHead>
              <TableHead className="text-right">Booked Price</TableHead>
              <TableHead className="text-right">Current Price</TableHead>
              <TableHead className="w-[50px]"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bookings.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="h-24 text-center">
                  No bookings found
                </TableCell>
              </TableRow>
            ) : (
              bookings.map((booking) => {
                const isCheaper = booking.fetched_price !== null && 
                                  booking.fetched_price < booking.price_paid;
                const isMoreExpensive = booking.fetched_price !== null && 
                                       booking.fetched_price > booking.price_paid;
                
                return (
                  <TableRow key={booking.id}>
                    <TableCell className="font-medium">
                      {booking.hotel_name}
                      {booking.hotel_url && (
                        <div className="text-xs text-muted-foreground truncate max-w-[250px]">
                          {booking.hotel_url}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      {formatDate(booking.check_in_date)} - {formatDate(booking.check_out_date)}
                    </TableCell>
                    <TableCell className="text-right">
                      ${formatPrice(booking.price_paid)}
                    </TableCell>
                    <TableCell className="text-right">
                      {loadingBookings[booking.id] ? (
                        <div className="flex justify-end items-center">
                          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        </div>
                      ) : booking.fetchError ? (
                        <div className="flex justify-end items-center text-amber-500 gap-1.5">
                          <AlertCircle className="h-4 w-4" />
                          <span className="text-sm">Price unavailable</span>
                        </div>
                      ) : booking.fetched_price !== null ? (
                        <div className="flex justify-end items-center gap-3">
                          <span className={
                            isCheaper ? "text-green-600 font-medium" : 
                            isMoreExpensive ? "text-red-600 font-medium" : ""
                          }>
                            ${formatPrice(booking.fetched_price)}
                          </span>
                          {booking.fetched_price_updated_at && (
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="text-xs text-muted-foreground">
                                    (Updated {format(new Date(booking.fetched_price_updated_at), 'MMM d, h:mm a')})
                                  </span>
                                </TooltipTrigger>
                                <TooltipContent>
                                  Price last checked on {format(new Date(booking.fetched_price_updated_at), 'PPpp')}
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          )}
                          {isCheaper && (
                            <RebookHotelButton 
                              hotelName={booking.hotel_name}
                              cheaperPrice={true}
                              checkInDate={booking.check_in_date}
                              checkOutDate={booking.check_out_date}
                              groupAdults={2} // Default to 2 adults
                            />
                          )}
                        </div>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleSyncBooking(booking.id)}
                          className="text-muted-foreground"
                        >
                          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
                          Check price
                        </Button>
                      )}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" className="h-8 w-8 p-0">
                            <span className="sr-only">Open menu</span>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleSyncBooking(booking.id)}>
                            <RefreshCw className="mr-2 h-4 w-4" />
                            <span>Check price</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => onUpdate(booking.id)}>
                            <Edit className="mr-2 h-4 w-4" />
                            <span>Update</span>
                          </DropdownMenuItem>
                          <DropdownMenuItem 
                            onClick={() => onDelete(booking.id)}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash className="mr-2 h-4 w-4" />
                            <span>Delete</span>
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};

export default BookingListView;
