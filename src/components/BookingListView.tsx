
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
      
      // In a real app, here you would update the fetched price in the database
      // For now we'll just show a success message
      toast.success(`Successfully synced booking ${id}`);
    } catch (error: any) {
      toast.error(`Failed to sync: ${error.message}`);
    } finally {
      setLoadingBookings(prev => ({ ...prev, [id]: false }));
    }
  };

  const handleSyncAll = async () => {
    setIsSyncingAll(true);
    try {
      // Simulate fetching all prices
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // In a real app, this would update all bookings
      onRefresh();
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
              Force Sync All
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
                          {isCheaper && (
                            <RebookHotelButton 
                              hotelName={booking.hotel_name}
                              cheaperPrice={true}
                              checkInDate={booking.check_in_date}
                              checkOutDate={booking.check_out_date}
                            />
                          )}
                        </div>
                      ) : (
                        <span className="text-muted-foreground">Not synced</span>
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
