
import React, { useState } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Mail, RefreshCw, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from 'sonner';
import { supabase } from '@/integrations/supabase/client';

/**
 * Function to check if a Gmail account is connected
 * @param user The user object from auth context
 * @returns Boolean indicating if Gmail is connected
 */
const isGmailAccountConnected = (user: any): boolean => {
  if (!user) return false;
  
  // Check if user has an email (basic validation)
  if (!user.email) {
    console.warn('User context missing email property');
    return false;
  }
  
  // Check if the user has explicitly connected Gmail
  return user.user_metadata?.gmail_connected === true;
};

interface GmailIntegrationStatusProps {
  onNewBookingsFound?: (count: number) => void;
}

const GmailIntegrationStatus: React.FC<GmailIntegrationStatusProps> = ({ 
  onNewBookingsFound 
}) => {
  const { user, isGmailConnected, connectGmail } = useAuth();
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncDate, setLastSyncDate] = useState<string | null>(null);
  
  // Use our dedicated function to check Gmail connection
  const gmailConnected = isGmailAccountConnected(user);

  const handleConnectGmail = async () => {
    if (gmailConnected) {
      toast.info('Gmail already connected');
      return;
    }
    
    await connectGmail();
  };

  const handleSyncGmail = async () => {
    if (!gmailConnected || !user) {
      toast.error('Gmail not connected. Please connect Gmail first.');
      return;
    }

    try {
      setIsSyncing(true);
      
      // Get the current session for the access token
      const { data: { session } } = await supabase.auth.getSession();
      
      if (!session?.provider_token) {
        toast.error('Unable to access Gmail. Please reconnect your account.');
        return;
      }
      
      // Call our edge function to process Gmail messages
      const { data, error } = await supabase.functions.invoke('process-gmail', {
        body: {
          accessToken: session.provider_token,
          userId: user.id
        }
      });
      
      if (error) {
        throw new Error(error.message);
      }
      
      const bookingsFound = data?.bookings?.length || 0;
      
      if (bookingsFound > 0) {
        toast.success(`Found ${bookingsFound} bookings from your Gmail`);
        if (onNewBookingsFound) {
          onNewBookingsFound(bookingsFound);
        }
      } else {
        toast.info('No new booking.com confirmations found in your Gmail');
      }
      
      // Update last sync date
      setLastSyncDate(new Date().toISOString());
      
      // Store the last sync date in user metadata
      await supabase.auth.updateUser({
        data: { last_gmail_sync: new Date().toISOString() }
      });
      
    } catch (error: any) {
      console.error('Error syncing Gmail:', error);
      toast.error(error.message || 'Error syncing Gmail');
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Gmail Integration</CardTitle>
        <CardDescription>
          Automatically import hotel reservations from your Gmail
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Mail className="mr-2 h-5 w-5 text-muted-foreground" />
              <div>
                <p className="font-medium">Gmail Account</p>
                <p className="text-sm text-muted-foreground">
                  {gmailConnected ? 'Connected' : 'Not connected'}
                </p>
                {lastSyncDate && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Last synced: {new Date(lastSyncDate).toLocaleString()}
                  </p>
                )}
              </div>
            </div>
            <Button 
              variant={gmailConnected ? "secondary" : "default"}
              onClick={handleConnectGmail}
              disabled={gmailConnected}
            >
              {gmailConnected ? 'Connected' : 'Connect Gmail'}
            </Button>
          </div>
          
          {gmailConnected && (
            <div className="pt-3">
              <Button 
                onClick={handleSyncGmail} 
                disabled={isSyncing} 
                variant="outline"
                className="w-full flex items-center gap-2"
              >
                {isSyncing ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Syncing with Gmail...
                  </>
                ) : (
                  <>
                    <RefreshCw className="h-4 w-4" />
                    Sync Bookings from Gmail
                  </>
                )}
              </Button>
              <p className="text-xs text-muted-foreground mt-2">
                We'll scan your inbox for booking.com confirmation emails and import them automatically.
              </p>
            </div>
          )}
          
          {!gmailConnected && (
            <div className="flex items-start mt-4 p-3 bg-amber-50 border border-amber-100 rounded-md">
              <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5 mr-2 flex-shrink-0" />
              <div className="text-sm text-amber-800">
                <p className="font-medium">Connect your Gmail account</p>
                <p className="mt-1">
                  To automatically import your hotel bookings from booking.com confirmation emails, 
                  please connect your Gmail account.
                </p>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default GmailIntegrationStatus;
