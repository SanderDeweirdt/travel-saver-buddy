
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/integrations/supabase/client';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { PlusCircle } from 'lucide-react';
import AddBookingModal from '@/components/AddBookingModal';
import BookingListView from '@/components/BookingListView';
import Header from '@/components/layout/Header';
import FetchBookingsButton from '@/components/FetchBookingsButton';
import { toast } from 'sonner';

interface Booking {
  id: string;
  hotel_name: string;
  hotel_url: string | null;
  price_paid: number;
  room_type: string | null;
  check_in_date: string;
  check_out_date: string;
  cancellation_date: string;
  created_at: string;
  fetched_price: number | null;
  fetched_price_updated_at: string | null;
}

const UserDashboard = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingBooking, setEditingBooking] = useState<Booking | null>(null);

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

  const handleUpdateBooking = (id: string) => {
    const booking = bookings.find(b => b.id === id);
    if (booking) {
      setEditingBooking(booking);
      setIsModalOpen(true);
    }
  };

  const handleDeleteBooking = async (id: string) => {
    try {
      const { error } = await supabase
        .from('bookings')
        .delete()
        .eq('id', id);

      if (error) {
        throw error;
      }

      // Update local state
      setBookings(bookings.filter(booking => booking.id !== id));
      toast.success('Booking deleted successfully');
    } catch (error: any) {
      console.error('Error deleting booking:', error.message);
      toast.error('Failed to delete booking');
    }
  };

  const onBookingAdded = () => {
    fetchBookings();
    setIsModalOpen(false);
    setEditingBooking(null);
    toast.success('Booking saved successfully!');
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />
      <div className="container max-w-7xl mx-auto px-4 py-8 flex-1">
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold">Your Bookings</h1>
          <div className="flex items-center gap-2">
            <FetchBookingsButton onFetchComplete={fetchBookings} />
            <Button 
              onClick={() => {
                setEditingBooking(null);
                setIsModalOpen(true);
              }}
              className="flex items-center"
            >
              <PlusCircle className="mr-2 h-4 w-4" />
              Add Booking
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-4">
            <div className="h-10 bg-muted rounded-md animate-pulse w-1/4"></div>
            <div className="border rounded-md animate-pulse">
              <div className="h-12 border-b"></div>
              <div className="h-16 border-b"></div>
              <div className="h-16 border-b"></div>
              <div className="h-16"></div>
            </div>
          </div>
        ) : (
          <BookingListView 
            bookings={bookings}
            onUpdate={handleUpdateBooking}
            onDelete={handleDeleteBooking}
            onRefresh={fetchBookings}
          />
        )}
      </div>

      <AddBookingModal 
        isOpen={isModalOpen} 
        onClose={() => {
          setIsModalOpen(false);
          setEditingBooking(null);
        }} 
        onBookingAdded={onBookingAdded}
        booking={editingBooking}
      />
    </div>
  );
};

export default UserDashboard;
