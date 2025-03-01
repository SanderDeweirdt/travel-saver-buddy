
import React from 'react';
import { cn } from '@/lib/utils';
import { DollarSign, TrendingUp } from 'lucide-react';

export interface SavingsData {
  totalSavings: number;
  currency: string;
  rebookings: number;
  averageSavingPercentage: number;
}

interface RecentSavingsProps {
  data: SavingsData;
  className?: string;
}

const RecentSavings = ({
  data,
  className
}: RecentSavingsProps) => {
  const { totalSavings, currency, rebookings, averageSavingPercentage } = data;
  
  return (
    <div className={cn(
      "bg-white border border-border rounded-xl overflow-hidden shadow-elevation-1 relative",
      className
    )}>
      <div className="absolute top-0 right-0 bottom-0 w-1/3 bg-primary/5 transform -skew-x-12" />
      
      <div className="relative p-5">
        <div className="flex items-center mb-3">
          <div className="bg-primary/10 p-2.5 rounded-full mr-3">
            <DollarSign className="h-5 w-5 text-primary" />
          </div>
          <h3 className="font-medium text-lg">Your Savings</h3>
        </div>
        
        <div className="flex flex-col">
          <div className="flex items-baseline space-x-1">
            <span className="text-3xl font-bold">{currency} {totalSavings.toFixed(2)}</span>
            <span className="text-sm text-green-600 flex items-center">
              <TrendingUp className="h-3.5 w-3.5 mr-0.5" />
              {averageSavingPercentage}%
            </span>
          </div>
          
          <p className="text-muted-foreground text-sm mt-1">
            Saved across {rebookings} rebookings
          </p>
        </div>
        
        <div className="mt-4 pt-4 border-t border-border">
          <p className="text-sm text-muted-foreground">
            Average savings of {averageSavingPercentage}% per booking
          </p>
        </div>
      </div>
    </div>
  );
};

export default RecentSavings;
