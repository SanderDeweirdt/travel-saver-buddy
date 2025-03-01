
import React from 'react';
import { Clock } from 'lucide-react';
import RecentSavings from '@/components/ui/RecentSavings';
import { Booking, SavingsData } from '@/utils/dashboardUtils';

interface SavingsSummarySectionProps {
  savingsData: SavingsData;
  bookings: Booking[];
}

const SavingsSummarySection: React.FC<SavingsSummarySectionProps> = ({ savingsData, bookings }) => {
  return (
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
  );
};

export default SavingsSummarySection;
