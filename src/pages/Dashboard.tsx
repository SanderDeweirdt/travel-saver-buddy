
import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Plus } from 'lucide-react';
import Header from '@/components/layout/Header';
import NavigationBar from '@/components/layout/NavigationBar';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';
import { fetchDashboardData } from '@/utils/dashboardUtils';
import PriceAlertsSection from '@/components/dashboard/PriceAlertsSection';
import SavingsSummarySection from '@/components/dashboard/SavingsSummarySection';
import BookingsListSection from '@/components/dashboard/BookingsListSection';
import type { Booking, PriceAlert, SavingsData } from '@/utils/dashboardUtils';

const Dashboard = () => {
  const { user } = useAuth();
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [priceAlerts, setPriceAlerts] = useState<PriceAlert[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  
  // Savings summary data
  const [savingsData, setSavingsData] = useState<SavingsData>({
    totalSavings: 0,
    currency: "$",
    rebookings: 0,
    averageSavingPercentage: 0
  });

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        setIsLoading(true);
        const { bookings, priceAlerts, savingsData, error } = await fetchDashboardData(user);
        
        if (error) {
          throw error;
        }
        
        setBookings(bookings);
        setPriceAlerts(priceAlerts);
        
        if (savingsData) {
          setSavingsData(savingsData);
        }
      } catch (error) {
        console.error('Error fetching data:', error);
        toast.error('Failed to load your bookings data');
      } finally {
        setIsLoading(false);
      }
    };
    
    if (user) {
      loadDashboardData();
    }
  }, [user]);
  
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
            <PriceAlertsSection 
              priceAlerts={priceAlerts}
              bookings={bookings}
              isLoading={isLoading}
              user={user}
              setPriceAlerts={setPriceAlerts}
              setBookings={setBookings}
              setSavingsData={setSavingsData}
              savingsData={savingsData}
            />
            
            {/* Savings summary */}
            <SavingsSummarySection 
              savingsData={savingsData}
              bookings={bookings}
            />
          </div>
          
          {/* Bookings list section */}
          <BookingsListSection 
            bookings={bookings}
            isLoading={isLoading}
          />
        </div>
      </main>
      
      <NavigationBar />
    </div>
  );
};

export default Dashboard;
