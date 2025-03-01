
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, Filter, TrendingDown } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import BookingCard from '@/components/ui/BookingCard';
import { Booking } from '@/utils/dashboardUtils';

interface BookingsListSectionProps {
  bookings: Booking[];
  isLoading: boolean;
}

const BookingsListSection: React.FC<BookingsListSectionProps> = ({ bookings, isLoading }) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState('upcoming');

  // Filter bookings based on search and active tab
  const filteredBookings = bookings.filter(booking => {
    const matchesSearch = searchQuery === '' || 
      booking.hotel_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      booking.location.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesTab = booking.status === activeTab;
    
    return matchesSearch && matchesTab;
  });

  return (
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
  );
};

export default BookingsListSection;
