
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus, TrendingDown, Search, Filter, Clock, ArrowUpRight } from 'lucide-react';
import Header from '@/components/layout/Header';
import NavigationBar from '@/components/layout/NavigationBar';
import PriceAlert from '@/components/ui/PriceAlert';
import BookingCard from '@/components/ui/BookingCard';
import RecentSavings from '@/components/ui/RecentSavings';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { supabase } from '@/integrations/supabase/client';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

// Types for our data
interface PriceAlert {
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

interface Booking {
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

interface SavingsData {
  totalSavings: number;
  currency: string;
  rebookings: number;
  averageSavingPercentage: number;
}

const Dashboard = () => {
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState('');
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [priceAlerts, setPriceAlerts] = useState<PriceAlert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('upcoming');
  
  // Savings summary data
  const [savingsData, setSavingsData] = useState<SavingsData>({
    totalSavings: 0,
    currency: "$",
    rebookings: 0,
    averageSavingPercentage: 0
  });

  useEffect(() => {
    if (!user) return;
    
    const fetchBookings = async () => {
      try {
        setIsLoading(true);
        
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
        
        setBookings(formattedBookings);
        
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
        
        setPriceAlerts(alerts);
        
        // Fetch savings data
        const { data: savingsData, error: savingsError } = await supabase
          .from('savings')
          .select('amount, currency');
        
        if (savingsError) {
          throw savingsError;
        }
        
        // Calculate total savings
        if (savingsData && savingsData.length > 0) {
          const totalSaved = savingsData.reduce((sum, item) => sum + Number(item.amount), 0);
          const rebookingsCount = savingsData.length;
          
          // Calculate average savings percentage
          // For simplicity, we're using a fixed percentage here
          // In a real app, you would calculate this based on original booking prices
          const avgSavingsPercentage = Math.round((totalSaved / (totalSaved * 4)) * 100);
          
          setSavingsData({
            totalSavings: totalSaved,
            currency: savingsData[0].currency || "$",
            rebookings: rebookingsCount,
            averageSavingPercentage: avgSavingsPercentage || 24
          });
        }
        
      } catch (error) {
        console.error('Error fetching data:', error);
        toast.error('Failed to load your bookings data');
      } finally {
        setIsLoading(false);
      }
    };
    
    fetchBookings();
  }, [user]);
  
  const dismissAlert = async (alertId: string) => {
    // In a real application, you might want to mark this alert as dismissed in the database
    setPriceAlerts(priceAlerts.filter(alert => alert.id !== alertId));
    toast.success('Alert dismissed');
  };
  
  const rebookHotel = async (alertId: string) => {
    try {
      // Find the booking and alert
      const alert = priceAlerts.find(a => a.id === alertId);
      const booking = bookings.find(b => b.id === alertId);
      
      if (!alert || !booking) {
        throw new Error('Booking not found');
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
          user_id: user?.id,
          booking_id: alertId,
          amount: savingsAmount,
          currency: booking.currency,
          description: `Rebooked ${booking.hotel_name} at a lower rate`
        }]);
      
      if (savingsError) throw savingsError;
      
      // Remove the alert
      setPriceAlerts(priceAlerts.filter(a => a.id !== alertId));
      
      // Update the booking in state
      setBookings(bookings.map(b => {
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

  // Filter bookings based on search and active tab
  const filteredBookings = bookings.filter(booking => {
    const matchesSearch = searchQuery === '' || 
      booking.hotel_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      booking.location.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesTab = booking.status === activeTab;
    
    return matchesSearch && matchesTab;
  });
  
  return (
    <div className="min-h-screen bg-muted/20">
      <Header />
      
      <main className="pt-24 pb-24 md:pb-16 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
            <div>
              <h1 className="text-3xl font-bold">Dashboard</h1>
              <p className="text-muted-foreground mt-1">Monitor your bookings and savings</p>
            </div>
            
            <div className="mt-4 md:mt-0">
              <Link to="/add-booking">
                <Button className="flex items-center">
                  <Plus className="h-4 w-4 mr-2" />
                  Add Booking
                </Button>
              </Link>
            </div>
          </div>
          
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
            {/* Price alerts section */}
            <div className="lg:col-span-2 space-y-6 animate-fade-in">
              <div className="flex items-center justify-between">
                <h2 className="text-xl font-semibold flex items-center">
                  <TrendingDown className="h-5 w-5 mr-2 text-green-600" />
                  Price Alerts
                </h2>
                <Button variant="ghost" size="sm" className="text-xs">
                  View All
                </Button>
              </div>
              
              {isLoading ? (
                <div className="flex justify-center p-8">
                  <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full"></div>
                </div>
              ) : priceAlerts.length > 0 ? (
                <div className="space-y-4">
                  {priceAlerts.map((alert) => (
                    <PriceAlert
                      key={alert.id}
                      hotelName={alert.hotelName}
                      location={alert.location}
                      checkInDate={alert.checkInDate}
                      checkOutDate={alert.checkOutDate}
                      originalPrice={alert.originalPrice}
                      newPrice={alert.newPrice}
                      currency={alert.currency}
                      imageUrl={alert.imageUrl}
                      onDismiss={() => dismissAlert(alert.id)}
                      onRebook={() => rebookHotel(alert.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="bg-white border border-border rounded-xl p-8 text-center animate-fade-in">
                  <div className="w-16 h-16 mx-auto bg-muted/50 rounded-full flex items-center justify-center mb-4">
                    <TrendingDown className="h-8 w-8 text-muted-foreground" />
                  </div>
                  <h3 className="text-lg font-medium mb-2">No Price Alerts</h3>
                  <p className="text-muted-foreground mb-6">
                    We'll notify you here when we find price drops for your bookings.
                  </p>
                  <Link to="/add-booking">
                    <Button variant="outline">
                      Add Your First Booking
                    </Button>
                  </Link>
                </div>
              )}
            </div>
            
            {/* Savings summary */}
            <div className="space-y-6 animate-fade-in animation-delay-200">
              <h2 className="text-xl font-semibold">Savings Summary</h2>
              
              <RecentSavings data={savingsData} />
              
              {bookings.length > 0 && (
                <div className="bg-white border border-border rounded-xl overflow-hidden shadow-elevation-1">
                  <div className="p-5">
                    <h3 className="font-medium mb-3 flex items-center">
                      <Clock className="h-4 w-4 mr-2 text-muted-foreground" />
                      Upcoming Cancellation Deadlines
                    </h3>
                    
                    <div className="space-y-4">
                      {bookings
                        .filter(booking => booking.cancellation_deadline)
                        .slice(0, 2) // Show only the first 2 upcoming deadlines
                        .map(booking => (
                          <div key={booking.id} className="flex items-start">
                            <div className="flex-shrink-0 w-2 h-2 rounded-full bg-orange-500 mt-1.5 mr-2"></div>
                            <div>
                              <p className="text-sm font-medium">{booking.hotel_name}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">
                                Free cancellation until {booking.cancellation_deadline}
                              </p>
                            </div>
                          </div>
                        ))}
                      
                      {bookings.filter(booking => booking.cancellation_deadline).length === 0 && (
                        <p className="text-sm text-muted-foreground">
                          No upcoming cancellation deadlines
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
          
          {/* Upcoming bookings section */}
          <div className="mt-10 animate-fade-in animation-delay-400">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6">
              <h2 className="text-xl font-semibold">Your Bookings</h2>
              
              <div className="mt-3 sm:mt-0 flex flex-col sm:flex-row space-y-3 sm:space-y-0 sm:space-x-3 w-full sm:w-auto">
                <div className="relative w-full sm:w-auto">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search bookings"
                    className="pl-9 w-full sm:w-[250px]"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                  />
                </div>
                
                <Button variant="outline" size="icon" className="h-10 w-10">
                  <Filter className="h-4 w-4" />
                </Button>
              </div>
            </div>
            
            <Tabs defaultValue="upcoming" onValueChange={setActiveTab}>
              <TabsList className="mb-6">
                <TabsTrigger value="upcoming">Upcoming</TabsTrigger>
                <TabsTrigger value="active">Active</TabsTrigger>
                <TabsTrigger value="past">Past</TabsTrigger>
                <TabsTrigger value="cancelled">Cancelled</TabsTrigger>
              </TabsList>
              
              <TabsContent value={activeTab} className="mt-0">
                {isLoading ? (
                  <div className="flex justify-center p-8">
                    <div className="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full"></div>
                  </div>
                ) : filteredBookings.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {filteredBookings.map((booking) => (
                      <BookingCard
                        key={booking.id}
                        id={booking.id}
                        hotelName={booking.hotel_name}
                        location={booking.location}
                        checkInDate={booking.check_in_date}
                        checkOutDate={booking.check_out_date}
                        price={booking.original_price}
                        currency={booking.currency}
                        roomType={booking.room_type}
                        cancellationDate={booking.cancellation_deadline}
                        imageUrl={booking.image_url}
                        priceDropped={booking.current_price < booking.original_price}
                        newPrice={booking.current_price < booking.original_price ? booking.current_price : undefined}
                        status={booking.status}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="bg-white border border-border rounded-xl p-8 text-center">
                    <div className="w-16 h-16 mx-auto bg-muted/50 rounded-full flex items-center justify-center mb-4">
                      <TrendingDown className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <h3 className="text-lg font-medium mb-2">No {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} Bookings</h3>
                    <p className="text-muted-foreground mb-6">
                      {activeTab === 'upcoming' ? 'Add your first hotel booking to start monitoring for price drops.' :
                       activeTab === 'active' ? 'You don\'t have any active trips right now.' :
                       activeTab === 'past' ? 'Your completed trips will appear here.' :
                       'Bookings you\'ve cancelled will appear here.'}
                    </p>
                    {activeTab === 'upcoming' && (
                      <Link to="/add-booking">
                        <Button variant="outline">
                          Add Your First Booking
                        </Button>
                      </Link>
                    )}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </div>
        </div>
      </main>
      
      <NavigationBar />
    </div>
  );
};

export default Dashboard;
