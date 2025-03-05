
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { PlusCircle, Calendar, MapPin, DollarSign, Clock, Hotel } from 'lucide-react';
import AddBookingModal from '@/components/AddBookingModal';
import { toast } from 'sonner';
import { format } from 'date-fns';

interface Booking {
  id: string;
  hotel_name: string;
  hotel_url: string;
  price_paid: number;
  room_type: string;
  check_in_date: string;
  check_out_date: string;
  cancellation_date: string;
  created_at: string;
}

const UserDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    if (!user) {
      navigate('/signin');
      return;
    }

    fetchBookings();
  }, [user, navigate]);

  const fetchBookings = async () => {
    try {
      setIsLoading(true);
      const { data, error } = await supabase
        .from('bookings')
        .select('*')
        .order('created_at', { ascending: false });

      if (error) {
        throw error;
      }

      setBookings(data || []);
    } catch (error: any) {
      console.error('Error fetching bookings:', error.message);
      toast.error('Failed to load bookings. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const onBookingAdded = () => {
    fetchBookings();
    setIsModalOpen(false);
    toast.success('Booking added successfully!');
  };

  // Format date string to a readable format
  const formatDate = (dateString: string) => {
    if (!dateString) return 'N/A';
    return format(new Date(dateString), 'MMM d, yyyy');
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container max-w-7xl mx-auto px-4 py-8">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">Your Bookings</h1>
          <Button 
            onClick={() => setIsModalOpen(true)}
            className="flex items-center"
          >
            <PlusCircle className="mr-2 h-4 w-4" />
            Add Booking
          </Button>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map((i) => (
              <Card key={i} className="p-6 h-[300px] flex flex-col animate-pulse">
                <div className="h-6 bg-muted rounded-md w-3/4 mb-4"></div>
                <div className="h-4 bg-muted rounded-md w-1/2 mb-2"></div>
                <div className="h-4 bg-muted rounded-md w-2/3 mb-6"></div>
                <div className="h-4 bg-muted rounded-md w-full mb-2"></div>
                <div className="h-4 bg-muted rounded-md w-4/5 mb-2"></div>
                <div className="h-4 bg-muted rounded-md w-3/5 mb-2"></div>
                <div className="h-4 bg-muted rounded-md w-2/3 mt-auto"></div>
              </Card>
            ))}
          </div>
        ) : bookings.length === 0 ? (
          <div className="text-center py-16">
            <Hotel className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-xl font-medium mb-2">No bookings yet</h3>
            <p className="text-muted-foreground mb-8">
              Start by adding your first hotel booking to monitor for price drops
            </p>
            <Button onClick={() => setIsModalOpen(true)}>
              <PlusCircle className="mr-2 h-4 w-4" />
              Add Your First Booking
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {bookings.map((booking) => (
              <Card key={booking.id} className="p-6 flex flex-col hover:shadow-md transition-shadow">
                <h3 className="text-xl font-semibold mb-2">{booking.hotel_name}</h3>
                <div className="flex items-start space-x-2 mb-1">
                  <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <p className="text-sm text-muted-foreground overflow-hidden text-ellipsis">
                    <a href={booking.hotel_url} target="_blank" rel="noopener noreferrer" className="hover:underline">
                      View Hotel
                    </a>
                  </p>
                </div>
                <div className="flex items-start space-x-2 mb-1">
                  <DollarSign className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <p className="text-sm text-muted-foreground">${booking.price_paid.toFixed(2)} - {booking.room_type}</p>
                </div>
                <div className="flex items-start space-x-2 mb-1">
                  <Calendar className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <p className="text-sm text-muted-foreground">
                    {formatDate(booking.check_in_date)} to {formatDate(booking.check_out_date)}
                  </p>
                </div>
                <div className="flex items-start space-x-2 mt-auto pt-4">
                  <Clock className="h-4 w-4 text-amber-500 mt-0.5" />
                  <p className="text-sm font-medium text-amber-500">
                    Free cancellation until {formatDate(booking.cancellation_date)}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <AddBookingModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        onBookingAdded={onBookingAdded}
      />
    </div>
  );
};

export default UserDashboard;
