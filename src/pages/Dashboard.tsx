
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Plus, TrendingDown, Search, Filter, Clock, ArrowUpRight } from 'lucide-react';
import Header from '@/components/layout/Header';
import NavigationBar from '@/components/layout/NavigationBar';
import PriceAlert from '@/components/ui/PriceAlert';
import BookingCard from '@/components/ui/BookingCard';
import RecentSavings from '@/components/ui/RecentSavings';
import FetchBookingsButton from '@/components/FetchBookingsButton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

// Mock data
const mockSavings = {
  totalSavings: 342.50,
  currency: "$",
  rebookings: 3,
  averageSavingPercentage: 24
};

const mockAlerts = [
  {
    id: "1",
    hotelName: "Grand Hyatt New York",
    location: "New York, NY",
    checkInDate: "Aug 15, 2023",
    checkOutDate: "Aug 20, 2023",
    originalPrice: 1249.50,
    newPrice: 989.75,
    currency: "$",
    imageUrl: "https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80"
  },
  {
    id: "2",
    hotelName: "Hilton San Francisco",
    location: "San Francisco, CA",
    checkInDate: "Sep 10, 2023",
    checkOutDate: "Sep 15, 2023",
    originalPrice: 899.00,
    newPrice: 749.00,
    currency: "$",
    imageUrl: "https://images.unsplash.com/photo-1618773928121-c32242e63f39?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80"
  }
];

const mockBookings = [
  {
    id: "1",
    hotelName: "Grand Hyatt New York",
    location: "New York, NY",
    checkInDate: "Aug 15, 2023",
    checkOutDate: "Aug 20, 2023",
    price: 1249.50,
    currency: "$",
    roomType: "King Room",
    cancellationDate: "Aug 13, 2023",
    imageUrl: "https://images.unsplash.com/photo-1566073771259-6a8506099945?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    priceDropped: true,
    newPrice: 989.75,
    status: 'upcoming' as 'upcoming' | 'active' | 'past' | 'cancelled'
  },
  {
    id: "2",
    hotelName: "Hilton San Francisco",
    location: "San Francisco, CA",
    checkInDate: "Sep 10, 2023",
    checkOutDate: "Sep 15, 2023",
    price: 899.00,
    currency: "$",
    roomType: "Double Queen Room",
    cancellationDate: "Sep 8, 2023",
    imageUrl: "https://images.unsplash.com/photo-1618773928121-c32242e63f39?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    priceDropped: true,
    newPrice: 749.00,
    status: 'upcoming' as 'upcoming' | 'active' | 'past' | 'cancelled'
  },
  {
    id: "3",
    hotelName: "Marriott London",
    location: "London, UK",
    checkInDate: "Oct 5, 2023",
    checkOutDate: "Oct 10, 2023",
    price: 1100.00,
    currency: "£",
    roomType: "Executive Suite",
    cancellationDate: "Oct 2, 2023",
    imageUrl: "https://images.unsplash.com/photo-1590073242678-70ee3fc28f8a?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    status: 'upcoming' as 'upcoming' | 'active' | 'past' | 'cancelled'
  }
];

const Dashboard = () => {
  const [searchQuery, setSearchQuery] = useState('');
  
  const dismissAlert = (alertId: string) => {
    console.log(`Dismissed alert ${alertId}`);
    // Would implement actual dismissal logic here
  };
  
  const rebookHotel = (alertId: string) => {
    console.log(`Rebooking for alert ${alertId}`);
    // Would implement actual rebooking logic here
  };
  
  const handleRefreshDashboard = () => {
    // This function would fetch updated data
    console.log('Refreshing dashboard data');
  };
  
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
              
              {mockAlerts.length > 0 ? (
                <div className="space-y-4">
                  {mockAlerts.map((alert) => (
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
              
              <RecentSavings data={mockSavings} />
              
              <div className="bg-white border border-border rounded-xl overflow-hidden shadow-elevation-1">
                <div className="p-5">
                  <h3 className="font-medium mb-3 flex items-center">
                    <Clock className="h-4 w-4 mr-2 text-muted-foreground" />
                    Upcoming Cancellation Deadlines
                  </h3>
                  
                  <div className="space-y-4">
                    <div className="flex items-start">
                      <div className="flex-shrink-0 w-2 h-2 rounded-full bg-orange-500 mt-1.5 mr-2"></div>
                      <div>
                        <p className="text-sm font-medium">Grand Hyatt New York</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Free cancellation until Aug 13
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-start">
                      <div className="flex-shrink-0 w-2 h-2 rounded-full bg-yellow-500 mt-1.5 mr-2"></div>
                      <div>
                        <p className="text-sm font-medium">Hilton San Francisco</p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          Free cancellation until Sep 8
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
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
                
                <div className="flex space-x-2">
                  <FetchBookingsButton onFetchComplete={handleRefreshDashboard} />
                  <Button 
                    variant="outline" 
                    size="icon" 
                    className="h-10 w-10"
                  >
                    <Filter className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
            
            <Tabs defaultValue="upcoming">
              <TabsList className="mb-6">
                <TabsTrigger value="upcoming">Upcoming</TabsTrigger>
                <TabsTrigger value="past">Past</TabsTrigger>
                <TabsTrigger value="cancelled">Cancelled</TabsTrigger>
              </TabsList>
              
              <TabsContent value="upcoming" className="mt-0">
                {mockBookings.length > 0 ? (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {mockBookings.map((booking) => (
                      <BookingCard
                        key={booking.id}
                        {...booking}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="bg-white border border-border rounded-xl p-8 text-center">
                    <div className="w-16 h-16 mx-auto bg-muted/50 rounded-full flex items-center justify-center mb-4">
                      <TrendingDown className="h-8 w-8 text-muted-foreground" />
                    </div>
                    <h3 className="text-lg font-medium mb-2">No Upcoming Bookings</h3>
                    <p className="text-muted-foreground mb-6">
                      Add your first hotel booking to start monitoring for price drops.
                    </p>
                    <Link to="/add-booking">
                      <Button variant="outline">
                        Add Your First Booking
                      </Button>
                    </Link>
                  </div>
                )}
              </TabsContent>
              
              <TabsContent value="past" className="mt-0">
                <div className="bg-white border border-border rounded-xl p-8 text-center">
                  <h3 className="text-lg font-medium mb-2">No Past Bookings</h3>
                  <p className="text-muted-foreground">
                    Your completed trips will appear here.
                  </p>
                </div>
              </TabsContent>
              
              <TabsContent value="cancelled" className="mt-0">
                <div className="bg-white border border-border rounded-xl p-8 text-center">
                  <h3 className="text-lg font-medium mb-2">No Cancelled Bookings</h3>
                  <p className="text-muted-foreground">
                    Bookings you've cancelled will appear here.
                  </p>
                </div>
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
