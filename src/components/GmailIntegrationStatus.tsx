import React, { useState } from 'react';
import { useAuth, GMAIL_API_SCOPES } from '@/contexts/AuthContext';
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
  const [retryCount, setRetryCount] = useState(0);
  const MAX_RETRIES = 3;
  
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
        console.error('No provider token available');
        toast.error('Unable to access Gmail. Please reconnect your account.');
        await reconnectGmail();
        return;
      }
      
      // Call our edge function to process Gmail messages
      const response = await processGmailWithRetry(session.provider_token, user.id);
      
      if (response.error) {
        throw new Error(response.error);
      }
      
      const bookingsFound = response.data?.bookings?.length || 0;
      
      if (bookingsFound > 0) {
        toast.success(`Found ${bookingsFound} bookings from your Gmail`);
        if (onNewBookingsFound) {
          onNewBookingsFound(bookingsFound);
        }
      } else {
        toast.info('No new booking.com confirmations found in your Gmail');
      }
      
      // Update last sync date
      const syncTime = new Date().toISOString();
      setLastSyncDate(syncTime);
      
      // Store the last sync date in user metadata
      await supabase.auth.updateUser({
        data: { 
          last_gmail_sync: syncTime,
          gmail_synced_bookings: (user.user_metadata?.gmail_synced_bookings || 0) + bookingsFound
        }
      });
      
      // Reset retry count on successful operation
      setRetryCount(0);
      
    } catch (error: any) {
      console.error('Error syncing Gmail:', error);
      
      if (error.message?.includes('reconnect') || error.message?.includes('token')) {
        await reconnectGmail();
      }
      
      toast.error(error.message || 'Error syncing Gmail');
    } finally {
      setIsSyncing(false);
    }
  };

  const reconnectGmail = async () => {
    toast.info('Reconnecting to Gmail...');
    try {
      await connectGmail();
      toast.success('Gmail reconnected. Please try syncing again.');
    } catch (error) {
      console.error('Failed to reconnect Gmail:', error);
      toast.error('Failed to reconnect Gmail. Please try again later.');
    }
  };

  const processGmailWithRetry = async (accessToken: string, userId: string, currentRetry = 0): Promise<any> => {
    try {
      console.log(`Attempt ${currentRetry + 1}/${MAX_RETRIES + 1} to process Gmail`);
      
      const { data, error } = await supabase.functions.invoke('process-gmail', {
        body: {
          accessToken,
          userId
        }
      });

      if (error) {
        console.error(`Gmail API error (attempt ${currentRetry + 1}):`, error);
        
        // Check if the error is related to authentication
        if ((error.message?.includes('403') || 
             error.message?.includes('401') || 
             error.message?.includes('authentication')) && 
            currentRetry < MAX_RETRIES) {
            
          console.log(`Token issue detected, attempt ${currentRetry + 1}/${MAX_RETRIES}. Refreshing token...`);
          
          // Refresh token by reconnecting to Gmail
          await connectGmail();
          
          // Wait a moment for the token to be refreshed
          await new Promise(resolve => setTimeout(resolve, 1000));
          
          // Get updated session
          const { data: { session: refreshedSession } } = await supabase.auth.getSession();
          
          if (!refreshedSession?.provider_token) {
            throw new Error('Failed to refresh token. Please try reconnecting your Gmail account.');
          }
          
          console.log('Token refreshed, retrying with new token');
          
          // Retry with new token
          return processGmailWithRetry(refreshedSession.provider_token, userId, currentRetry + 1);
        }
        
        throw error;
      }
      
      return { data, error: null };
      
    } catch (error: any) {
      console.error(`Error in Gmail API call (attempt ${currentRetry + 1}):`, error);
      
      // If we've reached max retries, give up
      if (currentRetry >= MAX_RETRIES) {
        return { 
          data: null, 
          error: `Gmail API error: ${error instanceof Error ? error.message : 'Unknown error'}. Please reconnect your Gmail account.` 
        };
      }
      
      // Otherwise retry
      console.log(`Error in Gmail API call, attempt ${currentRetry + 1}/${MAX_RETRIES}. Retrying...`);
      
      // Wait with exponential backoff before retrying
      const backoffTime = Math.pow(2, currentRetry) * 1000;
      await new Promise(resolve => setTimeout(resolve, backoffTime));
      
      return processGmailWithRetry(accessToken, userId, currentRetry + 1);
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
