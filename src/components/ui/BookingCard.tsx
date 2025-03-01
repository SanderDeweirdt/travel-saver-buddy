
import React from 'react';
import { cn } from '@/lib/utils';
import { Calendar, MapPin, ArrowRight, Clock, Flag } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export interface BookingCardProps {
  id: string;
  hotelName: string;
  location: string;
  checkInDate: string;
  checkOutDate: string;
  price: number;
  currency: string;
  roomType: string;
  cancellationDate?: string;
  imageUrl?: string;
  priceDropped?: boolean;
  newPrice?: number;
  status: 'upcoming' | 'active' | 'past' | 'cancelled';
  onClick?: () => void;
  className?: string;
}

const BookingCard = ({
  id,
  hotelName,
  location,
  checkInDate,
  checkOutDate,
  price,
  currency,
  roomType,
  cancellationDate,
  imageUrl,
  priceDropped,
  newPrice,
  status,
  onClick,
  className
}: BookingCardProps) => {
  
  const statusColors = {
    upcoming: "bg-blue-50 text-blue-700",
    active: "bg-green-50 text-green-700",
    past: "bg-gray-50 text-gray-700",
    cancelled: "bg-red-50 text-red-700"
  };
  
  const statusText = {
    upcoming: "Upcoming",
    active: "Active",
    past: "Past",
    cancelled: "Cancelled"
  };
  
  const savings = priceDropped && newPrice ? price - newPrice : 0;
  
  return (
    <div 
      className={cn(
        "group bg-white border border-border rounded-xl overflow-hidden shadow-elevation-1 transition-all duration-300 hover:shadow-elevation-2",
        className
      )}
      onClick={onClick}
    >
      <div className="relative">
        {imageUrl ? (
          <div className="w-full h-48 overflow-hidden">
            <img 
              src={imageUrl} 
              alt={hotelName} 
              className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105" 
            />
          </div>
        ) : (
          <div className="w-full h-48 bg-muted/50 flex items-center justify-center">
            <span className="text-muted-foreground">No image available</span>
          </div>
        )}
        
        <div className="absolute top-3 left-3 flex space-x-2">
          <Badge 
            className={cn(
              "font-medium border-0",
              statusColors[status]
            )}
          >
            {statusText[status]}
          </Badge>
          
          {priceDropped && newPrice && (
            <Badge className="bg-green-50 text-green-700 font-medium border-0">
              Price Drop
            </Badge>
          )}
        </div>
      </div>
      
      <div className="p-4">
        <div className="flex justify-between items-start">
          <div>
            <h3 className="font-medium text-lg">{hotelName}</h3>
            <p className="text-sm text-muted-foreground flex items-center mt-1">
              <MapPin className="h-3.5 w-3.5 mr-1" />
              {location}
            </p>
          </div>
          
          <div className="text-right">
            {priceDropped && newPrice ? (
              <div>
                <div className="flex items-baseline space-x-1.5 justify-end">
                  <span className="text-sm line-through text-muted-foreground">
                    {currency} {price}
                  </span>
                  <span className="text-base font-semibold text-green-600">
                    {currency} {newPrice}
                  </span>
                </div>
                <p className="text-xs text-green-600 mt-0.5">
                  Save {currency} {savings.toFixed(2)}
                </p>
              </div>
            ) : (
              <p className="text-base font-semibold">
                {currency} {price}
              </p>
            )}
          </div>
        </div>
        
        <div className="mt-3 flex items-center text-sm text-muted-foreground">
          <Calendar className="h-3.5 w-3.5 mr-1.5" />
          <span>{checkInDate}</span>
          <ArrowRight className="h-3 w-3 mx-1.5" />
          <span>{checkOutDate}</span>
        </div>
        
        <div className="mt-2 flex items-center text-sm text-muted-foreground">
          <Flag className="h-3.5 w-3.5 mr-1.5" />
          <span>{roomType}</span>
        </div>
        
        {cancellationDate && (
          <div className="mt-2 flex items-center text-sm text-muted-foreground">
            <Clock className="h-3.5 w-3.5 mr-1.5" />
            <span>Free cancellation until {cancellationDate}</span>
          </div>
        )}
        
        <Button 
          variant="ghost" 
          className="w-full mt-3 text-primary hover:text-primary hover:bg-primary/5"
        >
          View Details
        </Button>
      </div>
    </div>
  );
};

export default BookingCard;
