
import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, Plus, Calendar, CalendarCheck } from 'lucide-react';
import Header from '@/components/layout/Header';
import NavigationBar from '@/components/layout/NavigationBar';
import BookingCard from '@/components/ui/BookingCard';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils';

// Mock data
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
    status: 'upcoming' as const
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
    status: 'upcoming' as const
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
    status: 'upcoming' as const
  },
  {
    id: "4",
    hotelName: "Ritz-Carlton Tokyo",
    location: "Tokyo, Japan",
    checkInDate: "Dec 10, 2023",
    checkOutDate: "Dec 17, 2023",
    price: 2150.00,
    currency: "$",
    roomType: "Luxury Suite",
    cancellationDate: "Dec 1, 2023",
    imageUrl: "https://images.unsplash.com/photo-1542314831-068cd1dbfeeb?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    status: 'upcoming' as const
  },
  {
    id: "5",
    hotelName: "Four Seasons Paris",
    location: "Paris, France",
    checkInDate: "Jul 5, 2023",
    checkOutDate: "Jul 12, 2023",
    price: 2450.00,
    currency: "€",
    roomType: "Deluxe Room",
    imageUrl: "https://images.unsplash.com/photo-1549294413-26f195471c9a?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    status: 'past' as const
  },
  {
    id: "6",
    hotelName: "Waldorf Astoria Las Vegas",
    location: "Las Vegas, NV",
    checkInDate: "Jun 20, 2023",
    checkOutDate: "Jun 27, 2023",
    price: 1350.00,
    currency: "$",
    roomType: "Strip View Room",
    imageUrl: "https://images.unsplash.com/photo-1605346434674-a440ca2ae372?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1080&q=80",
    status: 'past' as const
  }
];

const Bookings = () => {
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [sortBy, setSortBy] = useState('date-asc');
  const [currentTab, setCurrentTab] = useState('upcoming');
  
  const filteredBookings = mockBookings.filter(booking => {
    // Filter by status
    if (booking.status !== currentTab) {
      return false;
    }
    
    // Filter by search query
    if (searchQuery.trim() !== '') {
      const query = searchQuery.toLowerCase();
      return (
        booking.hotelName.toLowerCase().includes(query) ||
        booking.location.toLowerCase().includes(query) ||
        booking.roomType.toLowerCase().includes(query)
      );
    }
    
    return true;
  });
  
  // Sort bookings
  const sortedBookings = [...filteredBookings].sort((a, b) => {
    if (sortBy === 'date-asc') {
      return new Date(a.checkInDate).getTime() - new Date(b.checkInDate).getTime();
    } else if (sortBy === 'date-desc') {
      return new Date(b.checkInDate).getTime() - new Date(a.checkInDate).getTime();
    } else if (sortBy === 'price-asc') {
      return a.price - b.price;
    } else if (sortBy === 'price-desc') {
      return b.price - a.price;
    }
    return 0;
  });
  
  const viewBookingDetails = (bookingId: string) => {
    navigate(`/booking/${bookingId}`);
  };
  
  return (
    <div className="min-h-screen bg-muted/20">
      <Header />
      
      <main className="pt-24 pb-24 md:pb-16 px-4">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8">
            <div>
              <h1 className="text-3xl font-bold">My Bookings</h1>
              <p className="text-muted-foreground mt-1">Manage all your hotel bookings</p>
            </div>
            
            <Button 
              className="mt-4 md:mt-0"
              onClick={() => navigate('/add-booking')}
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Booking
            </Button>
          </div>
          
          <div className="mb-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <Tabs 
              defaultValue="upcoming" 
              className="w-full sm:w-auto"
              onValueChange={setCurrentTab}
            >
              <TabsList>
                <TabsTrigger value="upcoming" className="flex items-center">
                  <Calendar className="h-4 w-4 mr-2" />
                  Upcoming
                </TabsTrigger>
                <TabsTrigger value="active" className="flex items-center">
                  <CalendarCheck className="h-4 w-4 mr-2" />
                  Active
                </TabsTrigger>
                <TabsTrigger value="past">Past</TabsTrigger>
                <TabsTrigger value="cancelled">Cancelled</TabsTrigger>
              </TabsList>
            </Tabs>
            
            <div className="flex w-full sm:w-auto items-center space-x-2">
              <div className="relative flex-1 sm:flex-auto">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search bookings"
                  className="pl-9 w-full sm:w-[250px]"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              
              <Button 
                variant="outline" 
                size="icon" 
                className={cn(
                  "h-10 w-10",
                  isFilterOpen && "bg-primary/10 text-primary"
                )}
                onClick={() => setIsFilterOpen(!isFilterOpen)}
              >
                <Filter className="h-4 w-4" />
              </Button>
            </div>
          </div>
          
          {isFilterOpen && (
            <div className="mb-6 bg-white border border-border rounded-lg p-4 animate-fade-in">
              <div className="flex flex-col sm:flex-row gap-4 items-end">
                <div className="w-full sm:w-[200px]">
                  <label className="text-sm font-medium mb-1.5 block">Sort By</label>
                  <Select value={sortBy} onValueChange={setSortBy}>
                    <SelectTrigger>
                      <SelectValue placeholder="Sort by" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="date-asc">Date (Earliest first)</SelectItem>
                      <SelectItem value="date-desc">Date (Latest first)</SelectItem>
                      <SelectItem value="price-asc">Price (Low to high)</SelectItem>
                      <SelectItem value="price-desc">Price (High to low)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                {/* Additional filters could be added here */}
                
                <div className="flex space-x-2">
                  <Button variant="outline" size="sm">
                    Reset
                  </Button>
                  <Button size="sm">
                    Apply Filters
                  </Button>
                </div>
              </div>
            </div>
          )}
          
          <div>
            <TabsContent value="upcoming" className="mt-0">
              {sortedBookings.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {sortedBookings.map((booking) => (
                    <BookingCard
                      key={booking.id}
                      {...booking}
                      onClick={() => viewBookingDetails(booking.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="bg-white border border-border rounded-xl p-8 text-center">
                  <div className="w-16 h-16 mx-auto bg-muted/50 rounded-full flex items-center justify-center mb-4">
                    <Calendar className="h-8 w-8 text-muted-foreground" />
                  </div>
                  <h3 className="text-lg font-medium mb-2">No Upcoming Bookings</h3>
                  <p className="text-muted-foreground mb-6">
                    Add your hotel bookings to start monitoring for price drops.
                  </p>
                  <Button variant="outline" onClick={() => navigate('/add-booking')}>
                    Add Booking
                  </Button>
                </div>
              )}
            </TabsContent>
            
            <TabsContent value="active" className="mt-0">
              <div className="bg-white border border-border rounded-xl p-8 text-center">
                <div className="w-16 h-16 mx-auto bg-muted/50 rounded-full flex items-center justify-center mb-4">
                  <CalendarCheck className="h-8 w-8 text-muted-foreground" />
                </div>
                <h3 className="text-lg font-medium mb-2">No Active Bookings</h3>
                <p className="text-muted-foreground mb-6">
                  Your current active bookings will appear here.
                </p>
                <Button variant="outline" onClick={() => navigate('/add-booking')}>
                  Add Booking
                </Button>
              </div>
            </TabsContent>
            
            <TabsContent value="past" className="mt-0">
              {mockBookings.filter(b => b.status === 'past').length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {mockBookings
                    .filter(b => b.status === 'past')
                    .map((booking) => (
                      <BookingCard
                        key={booking.id}
                        {...booking}
                        onClick={() => viewBookingDetails(booking.id)}
                      />
                    ))}
                </div>
              ) : (
                <div className="bg-white border border-border rounded-xl p-8 text-center">
                  <h3 className="text-lg font-medium mb-2">No Past Bookings</h3>
                  <p className="text-muted-foreground">
                    Your completed trips will appear here.
                  </p>
                </div>
              )}
            </TabsContent>
            
            <TabsContent value="cancelled" className="mt-0">
              <div className="bg-white border border-border rounded-xl p-8 text-center">
                <h3 className="text-lg font-medium mb-2">No Cancelled Bookings</h3>
                <p className="text-muted-foreground">
                  Bookings you've cancelled will appear here.
                </p>
              </div>
            </TabsContent>
          </div>
        </div>
      </main>
      
      <NavigationBar />
    </div>
  );
};

export default Bookings;
