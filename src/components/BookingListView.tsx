
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
  price_paid: number;
  check_in_date: string;
  check_out_date: string;
  fetched_price?: number;
  fetched_price_updated_at?: string;
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

  // Format date string to a readable format
  const formatDate = (dateString: string) => {
    if (!dateString) return 'N/A';
    return format(new Date(dateString), 'MMM d, yyyy');
  };

  const handleSyncBooking = async (id: string) => {
    // Set loading state for this specific booking
    setLoadingBookings(prev => ({ ...prev, [id]: true }));
    
    try {
      // Simulate fetching updated price
      await new Promise(resolve => setTimeout(resolve, 1500));
      
      // Generate a random price with 70% chance to be cheaper
      const booking = bookings.find(b => b.id === id);
      if (!booking) {
        throw new Error('Booking not found');
      }
      
      // Randomize price difference: 80% chance cheaper, 20% more expensive
      const priceDiff = Math.random() > 0.2 
        ? -(Math.random() * 50) // cheaper
        : (Math.random() * 20);  // more expensive
      
      const fetched_price = Math.max(0, booking.price_paid + priceDiff);
      
      // Update the fetched price in the database
      const { error } = await supabase
        .from('bookings')
        .update({ 
          fetched_price, 
          fetched_price_updated_at: new Date().toISOString() 
        })
        .eq('id', id);
      
      if (error) {
        throw error;
      }
      
      toast.success(`Successfully synced booking for ${booking.hotel_name}`);
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
      // Update all bookings with random prices
      const updates = bookings.map(async (booking) => {
        // Randomize price difference: 80% chance cheaper, 20% more expensive
        const priceDiff = Math.random() > 0.2 
          ? -(Math.random() * 50) // cheaper
          : (Math.random() * 20);  // more expensive
        
        const fetched_price = Math.max(0, booking.price_paid + priceDiff);
        
        return supabase
          .from('bookings')
          .update({ 
            fetched_price, 
            fetched_price_updated_at: new Date().toISOString() 
          })
          .eq('id', booking.id);
      });
      
      await Promise.all(updates);
      
      onRefresh(); // Refresh all bookings
      toast.success('All bookings synced successfully');
    } catch (error: any) {
      toast.error(`Failed to sync all bookings: ${error.message}`);
    } finally {
      setIsSyncingAll(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Your Bookings</h2>
        <Button 
          onClick={handleSyncAll}
          variant="outline"
          disabled={isSyncingAll}
          className="flex items-center gap-2"
        >
          {isSyncingAll ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Syncing...
            </>
          ) : (
            <>
              <RefreshCw className="h-4 w-4" />
              Check prices
            </>
          )}
        </Button>
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
                const isCheaper = booking.fetched_price !== undefined && booking.fetched_price < booking.price_paid;
                const isMoreExpensive = booking.fetched_price !== undefined && booking.fetched_price > booking.price_paid;
                
                return (
                  <TableRow key={booking.id}>
                    <TableCell className="font-medium">{booking.hotel_name}</TableCell>
                    <TableCell>
                      {formatDate(booking.check_in_date)} - {formatDate(booking.check_out_date)}
                    </TableCell>
                    <TableCell className="text-right">
                      ${booking.price_paid.toFixed(2)}
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
                      ) : booking.fetched_price !== undefined ? (
                        <div className="flex justify-end items-center gap-3">
                          <span className={
                            isCheaper ? "text-green-600 font-medium" : 
                            isMoreExpensive ? "text-red-600 font-medium" : ""
                          }>
                            ${booking.fetched_price.toFixed(2)}
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
