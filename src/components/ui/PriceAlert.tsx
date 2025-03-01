
import React from 'react';
import { cn } from '@/lib/utils';
import { TrendingDown, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';

export interface PriceAlertProps {
  hotelName: string;
  location: string;
  checkInDate: string;
  checkOutDate: string;
  originalPrice: number;
  newPrice: number;
  currency: string;
  imageUrl?: string;
  onDismiss?: () => void;
  onRebook?: () => void;
  className?: string;
}

const PriceAlert = ({
  hotelName,
  location,
  checkInDate,
  checkOutDate,
  originalPrice,
  newPrice,
  currency,
  imageUrl,
  onDismiss,
  onRebook,
  className
}: PriceAlertProps) => {
  const savings = originalPrice - newPrice;
  const savingsPercentage = Math.round((savings / originalPrice) * 100);
  
  return (
    <div className={cn(
      "bg-white border border-border rounded-xl overflow-hidden shadow-elevation-2 animate-slide-up",
      className
    )}>
      <div className="p-4 sm:p-5 flex flex-col">
        <div className="flex items-start space-x-3">
          <div className="bg-green-50 p-2 rounded-full">
            <TrendingDown className="h-5 w-5 text-green-600" />
          </div>
          
          <div className="flex-1">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-green-600">Price Drop Alert</p>
              <div className="flex items-center space-x-1">
                <span className="text-xs font-semibold text-green-600">{savingsPercentage}% off</span>
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-green-600"></span>
              </div>
            </div>
            
            <h3 className="font-medium mt-1">{hotelName}</h3>
            <p className="text-sm text-muted-foreground">{location}</p>
            
            <div className="mt-2 flex items-center justify-between">
              <div className="text-sm">
                <span className="text-muted-foreground">
                  {checkInDate} — {checkOutDate}
                </span>
              </div>
            </div>
            
            <div className="mt-3 flex items-end justify-between">
              <div>
                <div className="flex items-baseline space-x-1.5">
                  <span className="text-sm line-through text-muted-foreground">
                    {currency} {originalPrice}
                  </span>
                  <span className="text-lg font-semibold text-green-600">
                    {currency} {newPrice}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Save {currency} {savings.toFixed(2)}
                </p>
              </div>
              
              <div className="flex space-x-2">
                {onDismiss && (
                  <Button 
                    variant="ghost" 
                    size="sm" 
                    onClick={onDismiss}
                    className="h-9 text-sm"
                  >
                    Dismiss
                  </Button>
                )}
                
                {onRebook && (
                  <Button 
                    size="sm" 
                    onClick={onRebook} 
                    className="h-9 text-sm"
                  >
                    <span>Rebook</span>
                    <ExternalLink className="ml-1.5 h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PriceAlert;
