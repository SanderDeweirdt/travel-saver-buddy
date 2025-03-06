
import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';
import Header from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Mail, Link as LinkIcon } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { toast } from 'sonner';

const UserProfile = () => {
  const { user } = useAuth();
  const [fullName, setFullName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isGmailConnected, setIsGmailConnected] = useState(false);
  const [priceAlertThreshold, setPriceAlertThreshold] = useState(10);
  
  useEffect(() => {
    if (user) {
      setFullName(user.user_metadata?.full_name || '');
      
      // Check if user has connected Gmail (in a real app, this would check a DB field)
      // For now, we'll simulate this with a check of user metadata
      setIsGmailConnected(!!user.user_metadata?.gmail_connected);
    }
  }, [user]);

  const handleUpdateProfile = async () => {
    if (!user) return;
    
    try {
      setIsSaving(true);
      
      const { error } = await supabase.auth.updateUser({
        data: { full_name: fullName }
      });
      
      if (error) throw error;
      
      toast.success('Profile updated successfully');
    } catch (error: any) {
      console.error('Error updating profile:', error.message);
      toast.error('Failed to update profile');
    } finally {
      setIsSaving(false);
    }
  };

  const handleConnectGmail = () => {
    // This would actually initiate OAuth with Gmail
    toast.info('Gmail integration coming soon!');
    // For demo purposes, we'll simulate a successful connection
    setIsGmailConnected(true);
  };

  const handleSaveNotificationSettings = () => {
    // In a real app, this would save to a user_settings table
    toast.success(`Notification threshold set to ${priceAlertThreshold}%`);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />
      <div className="container max-w-3xl mx-auto px-4 py-8">
        <h1 className="text-3xl font-bold mb-8">Profile Settings</h1>
        
        <div className="space-y-6">
          {/* Personal Information */}
          <Card>
            <CardHeader>
              <CardTitle>Personal Information</CardTitle>
              <CardDescription>Update your personal details</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" value={user?.email || ''} disabled />
              </div>
              <div className="space-y-2">
                <Label htmlFor="name">Full Name</Label>
                <Input 
                  id="name" 
                  value={fullName} 
                  onChange={(e) => setFullName(e.target.value)} 
                />
              </div>
            </CardContent>
            <CardFooter>
              <Button onClick={handleUpdateProfile} disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Save Changes'}
              </Button>
            </CardFooter>
          </Card>
          
          {/* Connect Gmail */}
          <Card>
            <CardHeader>
              <CardTitle>Connect Gmail</CardTitle>
              <CardDescription>
                Connect your Gmail account to automatically import hotel reservations
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <Mail className="mr-2 h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium">Gmail Account</p>
                    <p className="text-sm text-muted-foreground">
                      {isGmailConnected ? 'Connected' : 'Not connected'}
                    </p>
                  </div>
                </div>
                <Button 
                  variant={isGmailConnected ? "secondary" : "default"}
                  onClick={handleConnectGmail}
                  disabled={isGmailConnected}
                >
                  {isGmailConnected ? 'Connected' : 'Connect'}
                </Button>
              </div>
            </CardContent>
          </Card>
          
          {/* Email Notification Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Email Notifications</CardTitle>
              <CardDescription>
                Configure when you want to receive email notifications
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="priceThreshold">
                  Notify me when prices are cheaper by at least:
                </Label>
                <div className="flex items-center">
                  <Input 
                    id="priceThreshold" 
                    type="number" 
                    min="1" 
                    max="100"
                    value={priceAlertThreshold} 
                    onChange={(e) => setPriceAlertThreshold(Number(e.target.value))}
                    className="max-w-[100px]" 
                  />
                  <span className="ml-2">%</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  You'll receive an email when we find a booking price that's at least {priceAlertThreshold}% cheaper than your booked price.
                </p>
              </div>
            </CardContent>
            <CardFooter>
              <Button onClick={handleSaveNotificationSettings}>
                Save Notification Settings
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default UserProfile;
