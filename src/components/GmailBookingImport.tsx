
import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Mail, RefreshCw, Inbox, CheckCircle } from 'lucide-react';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';

interface GmailBookingImportProps {
  onImportComplete?: () => void;
}

const GmailBookingImport: React.FC<GmailBookingImportProps> = ({ 
  onImportComplete 
}) => {
  const { user, isGmailConnected, connectGmail } = useAuth();
  const [isImporting, setIsImporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [bookingsFound, setBookingsFound] = useState(0);

  const simulateProgress = () => {
    let currentProgress = 0;
    const interval = setInterval(() => {
      currentProgress += Math.random() * 15;
      if (currentProgress > 95) {
        currentProgress = 95;
        clearInterval(interval);
      }
      setProgress(Math.min(currentProgress, 95));
    }, 500);
    
    return () => clearInterval(interval);
  };

  const handleConnectGmail = async () => {
    if (isGmailConnected) {
      toast.info('Gmail already connected');
      return;
    }
    
    await connectGmail();
  };

  const handleImportBookings = async () => {
    if (!isGmailConnected || !user) {
      toast.error('Gmail not connected. Please connect Gmail first.');
      return;
    }

    try {
      setIsImporting(true);
      setProgress(0);
      setBookingsFound(0);
      
      // Start progress animation
      const clearProgressSimulation = simulateProgress();
      
      // Get the current session for the access token
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session?.provider_token) {
        toast.error('Unable to access Gmail. Please reconnect your account.');
        return;
      }
      
      // Call our edge function to process Gmail messages with enhanced parsing rules
      const { data, error } = await supabase.functions.invoke('process-gmail', {
        body: {
          accessToken: session.provider_token,
          userId: user.id,
          parsingRules: {
            match: {
              from: "noreply@booking.com",
              subjectContains: "Your booking is confirmed"
            },
            extract: {
              confirmation_number: "regex:Confirmation:\\s*(\\d+)",
              hotel_name: "regex:Your booking is confirmed at\\s*(.*)",
              hotel_url: "linkContains:/hotel/",
              price_paid: "regex:Total price<\\/div>\\s*<div><span>€\\s*(\\d+\\.\\d{2})<\\/span>",
              room_type: "regex:Your reservation<\\/strong><\\/div>\\s*<div>\\d+ night[s]*, ([^<]+)",
              check_in_date_raw: "regex:Check-in\\s*\\w+,\\s*(\\w+ \\d{1,2}, \\d{4})",
              check_out_date_raw: "regex:Check-out\\s*\\w+,\\s*(\\w+ \\d{1,2}, \\d{4})",
              cancellation_date_raw: "regex:cancel for FREE until\\s*(\\w+ \\d{1,2}, \\d{4} \\d{2}:\\d{2} [AP]M)"
            }
          }
        }
      });
      
      if (error) {
        throw new Error(error.message);
      }
      
      const newBookings = data?.bookings?.length || 0;
      setBookingsFound(newBookings);
      
      // Complete the progress
      clearProgressSimulation();
      setProgress(100);
      
      if (newBookings > 0) {
        toast.success(`Imported ${newBookings} bookings from your Gmail`);
      } else {
        toast.info('No new booking.com confirmations found in your Gmail');
      }
      
      // Store the last import date in user metadata
      await supabase.auth.updateUser({
        data: { 
          last_gmail_import: new Date().toISOString(),
          gmail_imported_bookings: (user.user_metadata?.gmail_imported_bookings || 0) + newBookings
        }
      });
      
      // Notify parent component that import is complete
      if (onImportComplete) {
        setTimeout(onImportComplete, 1000);
      }
      
    } catch (error: any) {
      console.error('Error importing bookings from Gmail:', error);
      toast.error(error.message || 'Error importing bookings');
      setProgress(0);
    } finally {
      setIsImporting(false);
    }
  };

  return (
    <Card className="overflow-hidden">
      <CardHeader className="bg-primary/5 pb-4">
        <CardTitle className="flex items-center text-lg">
          <Inbox className="mr-2 h-5 w-5" />
          Import Bookings from Gmail
        </CardTitle>
      </CardHeader>
      
      <CardContent className="pt-5">
        {!isGmailConnected ? (
          <div className="text-center py-6">
            <Mail className="h-12 w-12 mx-auto text-muted-foreground opacity-50 mb-3" />
            <h3 className="text-lg font-medium mb-2">Connect Your Gmail Account</h3>
            <p className="text-muted-foreground mb-4 max-w-md mx-auto">
              Connect your Gmail account to automatically import your booking.com hotel reservations.
            </p>
            <Button onClick={handleConnectGmail}>
              Connect Gmail
            </Button>
          </div>
        ) : isImporting ? (
          <div className="py-6 space-y-4">
            <div className="text-center mb-2">
              <h3 className="text-lg font-medium">Importing Bookings...</h3>
              <p className="text-muted-foreground">
                Scanning your inbox for booking.com confirmation emails
              </p>
            </div>
            <Progress value={progress} className="w-full" />
          </div>
        ) : progress === 100 ? (
          <div className="text-center py-6">
            <CheckCircle className="h-12 w-12 mx-auto text-green-500 mb-3" />
            <h3 className="text-lg font-medium mb-2">Import Complete!</h3>
            <p className="text-muted-foreground">
              {bookingsFound ? (
                `Successfully imported ${bookingsFound} bookings from your Gmail account.`
              ) : (
                "No new bookings found in your Gmail account."
              )}
            </p>
          </div>
        ) : (
          <div className="py-4">
            <p className="mb-4">
              We'll scan your Gmail inbox for booking.com confirmation emails and automatically import them.
            </p>
            <ul className="space-y-2 mb-4">
              <li className="flex items-start">
                <CheckCircle className="h-4 w-4 text-green-500 mt-1 mr-2" />
                <span>Imports all your Booking.com hotel reservations</span>
              </li>
              <li className="flex items-start">
                <CheckCircle className="h-4 w-4 text-green-500 mt-1 mr-2" />
                <span>Extracts price, dates and hotel information</span>
              </li>
              <li className="flex items-start">
                <CheckCircle className="h-4 w-4 text-green-500 mt-1 mr-2" />
                <span>We only read confirmation emails, nothing else</span>
              </li>
            </ul>
          </div>
        )}
      </CardContent>
      
      {isGmailConnected && !isImporting && progress !== 100 && (
        <CardFooter className="bg-gray-50 border-t px-6 py-4">
          <Button 
            onClick={handleImportBookings} 
            className="w-full"
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Start Import
          </Button>
        </CardFooter>
      )}
      
      {progress === 100 && (
        <CardFooter className="bg-gray-50 border-t px-6 py-4">
          <Button 
            onClick={handleImportBookings} 
            variant="outline"
            className="w-full"
          >
            <RefreshCw className="mr-2 h-4 w-4" />
            Import Again
          </Button>
        </CardFooter>
      )}
    </Card>
  );
};

export default GmailBookingImport;
