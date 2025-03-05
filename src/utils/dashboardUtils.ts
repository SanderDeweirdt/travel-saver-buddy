
import { toast } from 'sonner';

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

// Mock data for bookings
const mockBookings: Booking[] = [
  {
    id: "1",
    hotel_name: "Grand Hyatt New York",
    location: "New York, NY",
    check_in_date: "Aug 15, 2023",
    check_out_date: "Aug 20, 2023",
    original_price: 1249.50,
    current_price: 989.75,
    currency: "$",
    room_type: "King Room",
    cancellation_deadline: "Aug 13, 2023",
    image_url: "https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    status: 'upcoming'
  },
  {
    id: "2",
    hotel_name: "Hilton San Francisco",
    location: "San Francisco, CA",
    check_in_date: "Sep 10, 2023",
    check_out_date: "Sep 15, 2023",
    original_price: 899.00,
    current_price: 749.00,
    currency: "$",
    room_type: "Double Queen Room",
    cancellation_deadline: "Sep 8, 2023",
    image_url: "https://images.unsplash.com/photo-1618773928121-c32242e63f39?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    status: 'upcoming'
  },
  {
    id: "3",
    hotel_name: "Marriott London",
    location: "London, UK",
    check_in_date: "Oct 5, 2023",
    check_out_date: "Oct 10, 2023",
    original_price: 1100.00,
    current_price: 1100.00,
    currency: "£",
    room_type: "Executive Suite",
    cancellation_deadline: "Oct 2, 2023",
    image_url: "https://images.unsplash.com/photo-1590073242678-70ee3fc28f8a?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    status: 'upcoming'
  }
];

// Mock data for savings
const mockSavingsData: SavingsData = {
  totalSavings: 409.75,
  currency: "$",
  rebookings: 2,
  averageSavingPercentage: 24
};

export const dismissAlert = async (alertId: string, setPriceAlerts: React.Dispatch<React.SetStateAction<PriceAlert[]>>) => {
  // In a real application, you might want to mark this alert as dismissed in the database
  setPriceAlerts(prev => prev.filter(alert => alert.id !== alertId));
  toast.success('Alert dismissed');
};

export const rebookHotel = async (
  alertId: string,
  user: any | null,
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
    
    // Simulate API call
    await new Promise(resolve => setTimeout(resolve, 800));
    
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

export const fetchDashboardData = async (user: any | null) => {
  if (!user) return { bookings: [], priceAlerts: [], savingsData: null, error: new Error('User not authenticated') };
  
  try {
    // Simulate API call delay
    await new Promise(resolve => setTimeout(resolve, 800));
    
    // Generate price alerts for bookings with price drops
    const alerts = mockBookings
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
    
    return {
      bookings: mockBookings,
      priceAlerts: alerts,
      savingsData: mockSavingsData,
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
