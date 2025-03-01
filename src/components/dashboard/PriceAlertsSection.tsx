
import React from 'react';
import { Link } from 'react-router-dom';
import { TrendingDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import PriceAlert from '@/components/ui/PriceAlert';
import { PriceAlert as PriceAlertType, dismissAlert, rebookHotel } from '@/utils/dashboardUtils';
import type { Booking, SavingsData } from '@/utils/dashboardUtils';
import { User } from '@supabase/supabase-js';

interface PriceAlertsSectionProps {
  priceAlerts: PriceAlertType[];
  bookings: Booking[];
  isLoading: boolean;
  user: User | null;
  setPriceAlerts: React.Dispatch<React.SetStateAction<PriceAlertType[]>>;
  setBookings: React.Dispatch<React.SetStateAction<Booking[]>>;
  setSavingsData: React.Dispatch<React.SetStateAction<SavingsData>>;
  savingsData: SavingsData;
}

const PriceAlertsSection: React.FC<PriceAlertsSectionProps> = ({
  priceAlerts,
  bookings,
  isLoading,
  user,
  setPriceAlerts,
  setBookings,
  setSavingsData,
  savingsData
}) => {
  const handleDismiss = (alertId: string) => {
    dismissAlert(alertId, setPriceAlerts);
  };

  const handleRebook = (alertId: string) => {
    rebookHotel(
      alertId,
      user,
      priceAlerts,
      bookings,
      setPriceAlerts,
      setBookings,
      setSavingsData,
      savingsData
    );
  };

  return (
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
              onDismiss={() => handleDismiss(alert.id)}
              onRebook={() => handleRebook(alert.id)}
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
  );
};

export default PriceAlertsSection;
