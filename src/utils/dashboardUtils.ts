
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';
import { User } from '@supabase/supabase-js';

export interface PriceAlert {
  id: string;
  hotelName: string;
  location: string;
  checkInDate: string;
  checkOutDate: string;
  originalPrice: number;
  newPrice: number;
  currency: string;
  imageUrl: string;
}

export interface Booking {
  id: string;
  hotel_name: string;
  location: string;
  check_in_date: string;
  check_out_date: string;
  original_price: number;
  current_price: number;
  currency: string;
  room_type: string;
  cancellation_deadline?: string;
  image_url?: string;
  status: 'upcoming' | 'active' | 'past' | 'cancelled';
}

export interface SavingsData {
  totalSavings: number;
  currency: string;
  rebookings: number;
  averageSavingPercentage: number;
}

export const dismissAlert = async (alertId: string, setPriceAlerts: React.Dispatch<React.SetStateAction<PriceAlert[]>>) => {
  // In a real application, you might want to mark this alert as dismissed in the database
  setPriceAlerts(prev => prev.filter(alert => alert.id !== alertId));
  toast.success('Alert dismissed');
};

export const rebookHotel = async (
  alertId: string,
  user: User | null,
  priceAlerts: PriceAlert[],
  bookings: Booking[],
  setPriceAlerts: React.Dispatch<React.SetStateAction<PriceAlert[]>>,
  setBookings: React.Dispatch<React.SetStateAction<Booking[]>>,
  setSavingsData: React.Dispatch<React.SetStateAction<SavingsData>>,
  savingsData: SavingsData
) => {
  try {
    // Find the booking and alert
    const alert = priceAlerts.find(a => a.id === alertId);
    const booking = bookings.find(b => b.id === alertId);
    
    if (!alert || !booking || !user) {
      throw new Error('Booking not found or user not authenticated');
    }
    
    // Calculate the savings amount
    const savingsAmount = booking.original_price - booking.current_price;
    
    // Update the booking with the new price
    const { error: updateError } = await supabase
      .from('bookings')
      .update({
        original_price: booking.current_price,
      })
      .eq('id', alertId);
    
    if (updateError) throw updateError;
    
    // Record the savings
    const { error: savingsError } = await supabase
      .from('savings')
      .insert([{
        user_id: user.id,
        booking_id: alertId,
        amount: savingsAmount,
        currency: booking.currency,
        description: `Rebooked ${booking.hotel_name} at a lower rate`
      }]);
    
    if (savingsError) throw savingsError;
    
    // Remove the alert
    setPriceAlerts(prev => prev.filter(a => a.id !== alertId));
    
    // Update the booking in state
    setBookings(prev => prev.map(b => {
      if (b.id === alertId) {
        return {
          ...b,
          original_price: b.current_price
        };
      }
      return b;
    }));
    
    // Update savings data
    setSavingsData({
      ...savingsData,
      totalSavings: savingsData.totalSavings + savingsAmount,
      rebookings: savingsData.rebookings + 1
    });
    
    toast.success('Hotel rebooked successfully at the lower rate!');
  } catch (error) {
    console.error('Error rebooking hotel:', error);
    toast.error('Failed to rebook the hotel. Please try again.');
  }
};

export const fetchDashboardData = async (user: User | null) => {
  if (!user) return { bookings: [], priceAlerts: [], savingsData: null, error: new Error('User not authenticated') };
  
  try {
    // Fetch bookings
    const { data: bookingsData, error: bookingsError } = await supabase
      .from('bookings')
      .select('*')
      .order('check_in_date', { ascending: true });
    
    if (bookingsError) {
      throw bookingsError;
    }
    
    // Format the bookings data
    const formattedBookings = bookingsData.map(booking => ({
      id: booking.id,
      hotel_name: booking.hotel_name,
      location: booking.location,
      check_in_date: new Date(booking.check_in_date).toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric', 
        year: 'numeric' 
      }),
      check_out_date: new Date(booking.check_out_date).toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric', 
        year: 'numeric' 
      }),
      original_price: booking.original_price,
      current_price: booking.current_price,
      currency: booking.currency,
      room_type: booking.room_type,
      cancellation_deadline: booking.cancellation_deadline ? 
        new Date(booking.cancellation_deadline).toLocaleDateString('en-US', { 
          month: 'short', 
          day: 'numeric' 
        }) : undefined,
      image_url: booking.image_url,
      status: booking.status,
    }));
    
    // Generate price alerts for bookings with price drops
    const alerts = formattedBookings
      .filter(booking => booking.current_price < booking.original_price)
      .map(booking => ({
        id: booking.id,
        hotelName: booking.hotel_name,
        location: booking.location,
        checkInDate: booking.check_in_date,
        checkOutDate: booking.check_out_date,
        originalPrice: booking.original_price,
        newPrice: booking.current_price,
        currency: booking.currency,
        imageUrl: booking.image_url || '',
      }));
    
    // Fetch savings data
    const { data: savingsData, error: savingsError } = await supabase
      .from('savings')
      .select('amount, currency');
    
    if (savingsError) {
      throw savingsError;
    }
    
    // Calculate total savings
    let processedSavingsData = null;
    
    if (savingsData && savingsData.length > 0) {
      const totalSaved = savingsData.reduce((sum, item) => sum + Number(item.amount), 0);
      const rebookingsCount = savingsData.length;
      
      // Calculate average savings percentage
      // For simplicity, we're using a fixed percentage here
      // In a real app, you would calculate this based on original booking prices
      const avgSavingsPercentage = Math.round((totalSaved / (totalSaved * 4)) * 100);
      
      processedSavingsData = {
        totalSavings: totalSaved,
        currency: savingsData[0].currency || "$",
        rebookings: rebookingsCount,
        averageSavingPercentage: avgSavingsPercentage || 24
      };
    } else {
      processedSavingsData = {
        totalSavings: 0,
        currency: "$",
        rebookings: 0,
        averageSavingPercentage: 0
      };
    }
    
    return {
      bookings: formattedBookings,
      priceAlerts: alerts,
      savingsData: processedSavingsData,
      error: null
    };
  } catch (error) {
    console.error('Error fetching data:', error);
    return {
      bookings: [],
      priceAlerts: [],
      savingsData: null,
      error
    };
  }
};
