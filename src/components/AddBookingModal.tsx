
import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar as CalendarIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { format } from 'date-fns';
import { toast } from 'sonner';

interface Booking {
  id: string;
  hotel_name: string;
  hotel_url: string;
  price_paid: number;
  room_type: string;
  check_in_date: string;
  check_out_date: string;
  cancellation_date: string;
}

interface AddBookingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onBookingAdded: () => void;
  booking?: Booking | null;
}

const AddBookingModal: React.FC<AddBookingModalProps> = ({ isOpen, onClose, onBookingAdded, booking }) => {
  const { user } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [hotelName, setHotelName] = useState('');
  const [hotelUrl, setHotelUrl] = useState('');
  const [pricePaid, setPricePaid] = useState('');
  const [roomType, setRoomType] = useState('');
  const [checkInDate, setCheckInDate] = useState<Date | undefined>(undefined);
  const [checkOutDate, setCheckOutDate] = useState<Date | undefined>(undefined);
  const [cancellationDate, setCancellationDate] = useState<Date | undefined>(undefined);

  // Populate form when editing a booking
  useEffect(() => {
    if (booking) {
      setHotelName(booking.hotel_name);
      setHotelUrl(booking.hotel_url || '');
      setPricePaid(booking.price_paid.toString());
      setRoomType(booking.room_type || '');
      setCheckInDate(booking.check_in_date ? new Date(booking.check_in_date) : undefined);
      setCheckOutDate(booking.check_out_date ? new Date(booking.check_out_date) : undefined);
      setCancellationDate(booking.cancellation_date ? new Date(booking.cancellation_date) : undefined);
    } else {
      resetForm();
    }
  }, [booking, isOpen]);

  const resetForm = () => {
    setHotelName('');
    setHotelUrl('');
    setPricePaid('');
    setRoomType('');
    setCheckInDate(undefined);
    setCheckOutDate(undefined);
    setCancellationDate(undefined);
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Validation
    if (!hotelName.trim()) {
      toast.error('Hotel name is required');
      return;
    }

    if (!pricePaid || isNaN(Number(pricePaid)) || Number(pricePaid) <= 0) {
      toast.error('Please enter a valid price');
      return;
    }

    if (!checkInDate || !checkOutDate || !cancellationDate) {
      toast.error('All dates are required');
      return;
    }

    if (checkInDate > checkOutDate) {
      toast.error('Check-in date must be before check-out date');
      return;
    }

    if (cancellationDate > checkInDate) {
      toast.error('Cancellation date must be before check-in date');
      return;
    }

    try {
      setIsSubmitting(true);

      const bookingData = {
        user_id: user?.id,
        hotel_name: hotelName,
        hotel_url: hotelUrl,
        price_paid: Number(pricePaid),
        room_type: roomType,
        check_in_date: checkInDate.toISOString(),
        check_out_date: checkOutDate.toISOString(),
        cancellation_date: cancellationDate.toISOString(),
      };

      if (booking) {
        // Update existing booking
        const { error } = await supabase
          .from('bookings')
          .update(bookingData)
          .eq('id', booking.id);

        if (error) throw error;
      } else {
        // Insert new booking
        const { error } = await supabase
          .from('bookings')
          .insert([bookingData]);

        if (error) throw error;
      }

      resetForm();
      onBookingAdded();
    } catch (error: any) {
      console.error('Error saving booking:', error.message);
      toast.error('Failed to save booking. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{booking ? 'Edit Booking' : 'Add New Booking'}</DialogTitle>
        </DialogHeader>
        
        <form onSubmit={handleSubmit} className="space-y-4 pt-4">
          <div className="space-y-2">
            <Label htmlFor="hotelName">Hotel Name</Label>
            <Input
              id="hotelName"
              placeholder="Enter hotel name"
              value={hotelName}
              onChange={(e) => setHotelName(e.target.value)}
              required
            />
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="hotelUrl">Hotel URL (optional)</Label>
            <Input
              id="hotelUrl"
              placeholder="https://example.com/hotel"
              value={hotelUrl}
              onChange={(e) => setHotelUrl(e.target.value)}
              // Removed type="url" to prevent browser's built-in validation
            />
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="pricePaid">Price Paid ($)</Label>
              <Input
                id="pricePaid"
                placeholder="199.99"
                value={pricePaid}
                onChange={(e) => setPricePaid(e.target.value)}
                type="number"
                step="0.01"
                min="0"
                required
              />
            </div>
            
            <div className="space-y-2">
              <Label htmlFor="roomType">Room Type</Label>
              <Input
                id="roomType"
                placeholder="Standard Double"
                value={roomType}
                onChange={(e) => setRoomType(e.target.value)}
              />
            </div>
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Check-in Date</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      "w-full justify-start text-left font-normal",
                      !checkInDate && "text-muted-foreground"
                    )}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {checkInDate ? format(checkInDate, "PPP") : "Select date"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={checkInDate}
                    onSelect={setCheckInDate}
                    initialFocus
                    className="p-3 pointer-events-auto"
                  />
                </PopoverContent>
              </Popover>
            </div>
            
            <div className="space-y-2">
              <Label>Check-out Date</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className={cn(
                      "w-full justify-start text-left font-normal",
                      !checkOutDate && "text-muted-foreground"
                    )}
                  >
                    <CalendarIcon className="mr-2 h-4 w-4" />
                    {checkOutDate ? format(checkOutDate, "PPP") : "Select date"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="start">
                  <Calendar
                    mode="single"
                    selected={checkOutDate}
                    onSelect={setCheckOutDate}
                    initialFocus
                    className="p-3 pointer-events-auto"
                    disabled={(date) => {
                      return checkInDate ? date < checkInDate : false;
                    }}
                  />
                </PopoverContent>
              </Popover>
            </div>
          </div>
          
          <div className="space-y-2">
            <Label>Free Cancellation Until</Label>
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={cn(
                    "w-full justify-start text-left font-normal",
                    !cancellationDate && "text-muted-foreground"
                  )}
                >
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {cancellationDate ? format(cancellationDate, "PPP") : "Select date"}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  mode="single"
                  selected={cancellationDate}
                  onSelect={setCancellationDate}
                  initialFocus
                  className="p-3 pointer-events-auto"
                />
              </PopoverContent>
            </Popover>
          </div>
          
          <div className="flex justify-end space-x-3 pt-4">
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Saving...' : booking ? 'Update Booking' : 'Add Booking'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};

export default AddBookingModal;
