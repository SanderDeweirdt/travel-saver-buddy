
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { format } from 'date-fns';
import { Calendar as CalendarIcon, Building, MapPin, Bed, DollarSign } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { Calendar } from '@/components/ui/calendar';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import Header from '@/components/layout/Header';
import NavigationBar from '@/components/layout/NavigationBar';
import { useAuth } from '@/contexts/AuthContext';
import { supabase, ensureUserProfile } from '@/integrations/supabase/client';
import { Database } from '@/integrations/supabase/types';

type BookingStatus = Database['public']['Enums']['booking_status'];

interface FormData {
  hotelName: string;
  location: string;
  roomType: string;
  price: string;
  currency: string;
}

const AddBooking = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [checkInDate, setCheckInDate] = useState<Date | undefined>(undefined);
  const [checkOutDate, setCheckOutDate] = useState<Date | undefined>(undefined);
  const [cancellationDate, setCancellationDate] = useState<Date | undefined>(undefined);
  const [profileVerified, setProfileVerified] = useState(false);
  
  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
    watch,
  } = useForm<FormData>({
    defaultValues: {
      currency: 'USD',
      roomType: 'Standard Room',
    }
  });
  
  const watchCurrency = watch('currency');
  
  // Check if profile exists on component mount
  useEffect(() => {
    const verifyUserProfile = async () => {
      if (!user) return;
      
      try {
        // Ensure user profile exists
        const profileSuccess = await ensureUserProfile(user.id, user.email);
        
        if (profileSuccess) {
          setProfileVerified(true);
          console.log('User profile verified successfully');
        } else {
          console.error('Failed to verify user profile');
          toast.error('Unable to verify your user profile. Please try signing out and in again.');
        }
      } catch (error) {
        console.error('Error verifying profile:', error);
        toast.error('Error checking your user profile. Please try again later.');
      }
    };
    
    verifyUserProfile();
  }, [user]);
  
  const validateDates = () => {
    if (!checkInDate) {
      toast.error('Please select a check-in date');
      return false;
    }
    
    if (!checkOutDate) {
      toast.error('Please select a check-out date');
      return false;
    }
    
    if (checkInDate >= checkOutDate) {
      toast.error('Check-out date must be after check-in date');
      return false;
    }
    
    if (cancellationDate && cancellationDate > checkInDate) {
      toast.error('Cancellation deadline must be before check-in date');
      return false;
    }
    
    return true;
  };
  
  const onSubmit = async (data: FormData) => {
    if (!validateDates() || !user) return;
    
    if (!profileVerified) {
      toast.error('Your user profile is not ready. Please try signing out and in again.');
      return;
    }
    
    try {
      setIsSubmitting(true);
      
      // Double-check profile exists right before submitting
      const profileExists = await ensureUserProfile(user.id, user.email);
      if (!profileExists) {
        throw new Error('Unable to verify your user profile');
      }
      
      const bookingData = {
        user_id: user.id,
        hotel_name: data.hotelName,
        location: data.location,
        room_type: data.roomType,
        check_in_date: format(checkInDate!, 'yyyy-MM-dd'),
        check_out_date: format(checkOutDate!, 'yyyy-MM-dd'),
        cancellation_deadline: cancellationDate ? format(cancellationDate, 'yyyy-MM-dd') : null,
        original_price: parseFloat(data.price),
        current_price: parseFloat(data.price), // Initially the same as original price
        currency: data.currency,
        status: 'upcoming' as BookingStatus,
      };
      
      const { error } = await supabase
        .from('bookings')
        .insert(bookingData);
      
      if (error) {
        console.error('Error details:', error);
        if (error.code === '23503' && error.message.includes('profiles')) {
          throw new Error('Your user profile does not exist. Please sign out and sign in again.');
        }
        throw error;
      }
      
      toast.success('Booking added successfully');
      navigate('/dashboard');
    } catch (error: any) {
      console.error('Error adding booking:', error);
      toast.error(error.message || 'Failed to add booking. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };
  
  return (
    <div className="min-h-screen bg-muted/20">
      <Header />
      
      <main className="pt-24 pb-24 md:pb-16 px-4">
        <div className="max-w-3xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl font-bold">Add Booking</h1>
            <p className="text-muted-foreground mt-1">Enter your hotel booking details</p>
          </div>
          
          <div className="bg-white border border-border rounded-xl p-6 shadow-elevation-1">
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
              <div className="space-y-4">
                <div>
                  <Label htmlFor="hotelName" className="flex items-center gap-2">
                    <Building className="h-4 w-4 text-muted-foreground" />
                    Hotel Name
                  </Label>
                  <div className="mt-1.5">
                    <Input
                      id="hotelName"
                      type="text"
                      {...register('hotelName', { required: 'Hotel name is required' })}
                      placeholder="e.g. Grand Hyatt New York"
                      className={cn(errors.hotelName && 'border-destructive')}
                    />
                    {errors.hotelName && (
                      <p className="mt-1 text-sm text-destructive">{errors.hotelName.message}</p>
                    )}
                  </div>
                </div>
                
                <div>
                  <Label htmlFor="location" className="flex items-center gap-2">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    Location
                  </Label>
                  <div className="mt-1.5">
                    <Input
                      id="location"
                      type="text"
                      {...register('location', { required: 'Location is required' })}
                      placeholder="e.g. New York, NY"
                      className={cn(errors.location && 'border-destructive')}
                    />
                    {errors.location && (
                      <p className="mt-1 text-sm text-destructive">{errors.location.message}</p>
                    )}
                  </div>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label className="flex items-center gap-2">
                      <CalendarIcon className="h-4 w-4 text-muted-foreground" />
                      Check-in Date
                    </Label>
                    <div className="mt-1.5">
                      <Popover>
                        <PopoverTrigger asChild>
                          <Button
                            variant="outline"
                            className={cn(
                              "w-full justify-start text-left font-normal",
                              !checkInDate && "text-muted-foreground",
                              errors.hotelName && "border-destructive"
                            )}
                          >
                            <CalendarIcon className="mr-2 h-4 w-4" />
                            {checkInDate ? format(checkInDate, "PPP") : "Select date"}
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-auto p-0">
                          <Calendar
                            mode="single"
                            selected={checkInDate}
                            onSelect={setCheckInDate}
                            initialFocus
                            disabled={(date) => date < new Date()}
                          />
                        </PopoverContent>
                      </Popover>
                    </div>
                  </div>
                  
                  <div>
                    <Label className="flex items-center gap-2">
                      <CalendarIcon className="h-4 w-4 text-muted-foreground" />
                      Check-out Date
                    </Label>
                    <div className="mt-1.5">
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
                        <PopoverContent className="w-auto p-0">
                          <Calendar
                            mode="single"
                            selected={checkOutDate}
                            onSelect={setCheckOutDate}
                            initialFocus
                            disabled={(date) => date < (checkInDate || new Date())}
                          />
                        </PopoverContent>
                      </Popover>
                    </div>
                  </div>
                </div>
                
                <div>
                  <Label className="flex items-center gap-2">
                    <CalendarIcon className="h-4 w-4 text-muted-foreground" />
                    Cancellation Deadline (Optional)
                  </Label>
                  <div className="mt-1.5">
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
                      <PopoverContent className="w-auto p-0">
                        <Calendar
                          mode="single"
                          selected={cancellationDate}
                          onSelect={setCancellationDate}
                          initialFocus
                          disabled={(date) => checkInDate ? date > checkInDate : false}
                        />
                      </PopoverContent>
                    </Popover>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Last day to cancel without penalties
                    </p>
                  </div>
                </div>
                
                <div>
                  <Label htmlFor="roomType" className="flex items-center gap-2">
                    <Bed className="h-4 w-4 text-muted-foreground" />
                    Room Type
                  </Label>
                  <div className="mt-1.5">
                    <Select
                      defaultValue="Standard Room"
                      onValueChange={(value) => setValue('roomType', value)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select room type" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Standard Room">Standard Room</SelectItem>
                        <SelectItem value="Deluxe Room">Deluxe Room</SelectItem>
                        <SelectItem value="Suite">Suite</SelectItem>
                        <SelectItem value="Executive Suite">Executive Suite</SelectItem>
                        <SelectItem value="Double Room">Double Room</SelectItem>
                        <SelectItem value="Single Room">Single Room</SelectItem>
                        <SelectItem value="Twin Room">Twin Room</SelectItem>
                        <SelectItem value="Apartment">Apartment</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="price" className="flex items-center gap-2">
                      <DollarSign className="h-4 w-4 text-muted-foreground" />
                      Price
                    </Label>
                    <div className="mt-1.5">
                      <Input
                        id="price"
                        type="number"
                        step="0.01"
                        min="0"
                        {...register('price', { 
                          required: 'Price is required',
                          pattern: {
                            value: /^\d+(\.\d{1,2})?$/,
                            message: 'Please enter a valid price'
                          }
                        })}
                        placeholder="e.g. 599.99"
                        className={cn(errors.price && 'border-destructive')}
                      />
                      {errors.price && (
                        <p className="mt-1 text-sm text-destructive">{errors.price.message}</p>
                      )}
                    </div>
                  </div>
                  
                  <div>
                    <Label htmlFor="currency" className="flex items-center gap-2">
                      Currency
                    </Label>
                    <div className="mt-1.5">
                      <Select
                        defaultValue="USD"
                        onValueChange={(value) => setValue('currency', value)}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select currency" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="USD">$ USD</SelectItem>
                          <SelectItem value="EUR">€ EUR</SelectItem>
                          <SelectItem value="GBP">£ GBP</SelectItem>
                          <SelectItem value="CAD">$ CAD</SelectItem>
                          <SelectItem value="AUD">$ AUD</SelectItem>
                          <SelectItem value="JPY">¥ JPY</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="pt-4 flex flex-col-reverse sm:flex-row gap-3 sm:justify-end">
                <Button 
                  type="button" 
                  variant="outline" 
                  onClick={() => navigate('/dashboard')}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <span className="animate-spin mr-2">
                        <svg className="h-4 w-4" viewBox="0 0 24 24">
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                            fill="none"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                          />
                        </svg>
                      </span>
                      Adding Booking...
                    </>
                  ) : (
                    'Add Booking'
                  )}
                </Button>
              </div>
            </form>
          </div>
        </div>
      </main>
      
      <NavigationBar />
    </div>
  );
};

export default AddBooking;
