
import React, { useState, useEffect } from 'react';
import { useAuth } from '@/contexts/AuthContext';
import { supabase } from '@/integrations/supabase/client';
import Header from '@/components/layout/Header';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Mail, Bell, AlertCircle, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";

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

const UserProfile = () => {
  const { user, isGmailConnected, connectGmail } = useAuth();
  const [fullName, setFullName] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isConnectingGmail, setIsConnectingGmail] = useState(false);
  const [priceAlertThreshold, setPriceAlertThreshold] = useState(10);
  const [preferredCurrency, setPreferredCurrency] = useState('USD');
  const [timezone, setTimezone] = useState('UTC');
  const [notificationMethod, setNotificationMethod] = useState('email');
  
  // Use our new function to get Gmail connection status
  const gmailConnected = isGmailAccountConnected(user);
  
  useEffect(() => {
    if (user) {
      setFullName(user.user_metadata?.full_name || '');
      
      // Load user preferences from metadata
      setPreferredCurrency(user.user_metadata?.preferred_currency || 'USD');
      setTimezone(user.user_metadata?.timezone || 'UTC');
      setNotificationMethod(user.user_metadata?.notification_method || 'email');
      setPriceAlertThreshold(user.user_metadata?.price_alert_threshold || 10);
    }
  }, [user]);

  const handleUpdateProfile = async () => {
    if (!user) return;
    
    try {
      setIsSaving(true);
      
      const { error } = await supabase.auth.updateUser({
        data: { 
          full_name: fullName,
          preferred_currency: preferredCurrency,
          timezone: timezone,
          notification_method: notificationMethod,
          price_alert_threshold: priceAlertThreshold
        }
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

  const handleConnectGmail = async () => {
    // If Gmail is already connected, just show a notification
    if (gmailConnected) {
      toast.info('Gmail is already connected to your account');
      return;
    }
    
    try {
      setIsConnectingGmail(true);
      
      // Check user authentication
      if (!user) {
        toast.error('You must be logged in to connect Gmail');
        return;
      }
      
      // Check if user has a valid email
      if (!user.email) {
        toast.error('User account does not have a valid email');
        return;
      }
      
      // Initiate the Gmail connection process with updated scopes
      await connectGmail();
      
    } catch (error: any) {
      console.error('Error connecting Gmail:', error);
      toast.error('Failed to connect Gmail. Please try again.');
    } finally {
      setIsConnectingGmail(false);
    }
  };

  // Add the missing handleSaveNotificationSettings function
  const handleSaveNotificationSettings = async () => {
    if (!user) return;
    
    try {
      setIsSaving(true);
      
      const { error } = await supabase.auth.updateUser({
        data: { 
          notification_method: notificationMethod,
          price_alert_threshold: priceAlertThreshold
        }
      });
      
      if (error) throw error;
      
      toast.success('Notification settings updated successfully');
    } catch (error: any) {
      console.error('Error updating notification settings:', error.message);
      toast.error('Failed to update notification settings');
    } finally {
      setIsSaving(false);
    }
  };

  // Common timezones for the select dropdown
  const timezones = [
    { value: 'UTC', label: 'UTC (Coordinated Universal Time)' },
    { value: 'America/New_York', label: 'Eastern Time (ET)' },
    { value: 'America/Chicago', label: 'Central Time (CT)' },
    { value: 'America/Denver', label: 'Mountain Time (MT)' },
    { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
    { value: 'Europe/London', label: 'London (GMT)' },
    { value: 'Europe/Paris', label: 'Central European Time (CET)' },
    { value: 'Asia/Tokyo', label: 'Japan Standard Time (JST)' },
    { value: 'Australia/Sydney', label: 'Australian Eastern Time (AET)' }
  ];

  // Common currencies for the select dropdown
  const currencies = [
    { value: 'USD', label: 'USD ($)' },
    { value: 'EUR', label: 'EUR (€)' },
    { value: 'GBP', label: 'GBP (£)' },
    { value: 'JPY', label: 'JPY (¥)' },
    { value: 'CAD', label: 'CAD ($)' },
    { value: 'AUD', label: 'AUD ($)' },
    { value: 'CHF', label: 'CHF (Fr)' }
  ];

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
                      {gmailConnected ? 'Connected' : 'Not connected'}
                    </p>
                    {gmailConnected && (
                      <p className="text-xs text-muted-foreground mt-1">
                        We will automatically scan for booking.com confirmation emails
                      </p>
                    )}
                  </div>
                </div>
                <Button 
                  variant={gmailConnected ? "secondary" : "default"}
                  onClick={handleConnectGmail}
                  disabled={isConnectingGmail || gmailConnected}
                >
                  {isConnectingGmail ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Connecting...
                    </>
                  ) : gmailConnected ? (
                    'Connected'
                  ) : (
                    'Connect Gmail'
                  )}
                </Button>
              </div>
              
              {!gmailConnected && !isConnectingGmail && (
                <div className="mt-4 p-3 bg-amber-50 border border-amber-100 rounded-md">
                  <div className="flex">
                    <AlertCircle className="h-5 w-5 text-amber-500 mt-0.5 mr-2 flex-shrink-0" />
                    <div className="text-sm text-amber-800">
                      <p>Connecting Gmail will allow Travel Buddy to:</p>
                      <ul className="list-disc pl-5 mt-1 space-y-1">
                        <li>Read your booking.com confirmation emails</li>
                        <li>Automatically import hotel reservations</li>
                        <li>Monitor price changes for your bookings</li>
                      </ul>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
          
          {/* Preferences */}
          <Card>
            <CardHeader>
              <CardTitle>Preferences</CardTitle>
              <CardDescription>
                Customize your experience with Travel Buddy
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="currency">Preferred Currency</Label>
                <Select
                  value={preferredCurrency}
                  onValueChange={setPreferredCurrency}
                >
                  <SelectTrigger id="currency" className="w-full">
                    <SelectValue placeholder="Select currency" />
                  </SelectTrigger>
                  <SelectContent>
                    {currencies.map(currency => (
                      <SelectItem key={currency.value} value={currency.value}>
                        {currency.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <Label htmlFor="timezone">Timezone</Label>
                <Select
                  value={timezone}
                  onValueChange={setTimezone}
                >
                  <SelectTrigger id="timezone" className="w-full">
                    <SelectValue placeholder="Select timezone" />
                  </SelectTrigger>
                  <SelectContent>
                    {timezones.map(tz => (
                      <SelectItem key={tz.value} value={tz.value}>
                        {tz.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-sm text-muted-foreground">
                  Your timezone is used for displaying booking dates and scheduling notifications.
                </p>
              </div>
            </CardContent>
            <CardFooter>
              <Button onClick={handleUpdateProfile} disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Save Preferences'}
              </Button>
            </CardFooter>
          </Card>
          
          {/* Notification Settings */}
          <Card>
            <CardHeader>
              <CardTitle>Notification Settings</CardTitle>
              <CardDescription>
                Configure when and how you want to receive notifications
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <Label>Notification Method</Label>
                <RadioGroup 
                  value={notificationMethod} 
                  onValueChange={setNotificationMethod}
                  className="flex flex-col space-y-2"
                >
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="email" id="method-email" />
                    <Label htmlFor="method-email" className="cursor-pointer">Email</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="push" id="method-push" />
                    <Label htmlFor="method-push" className="cursor-pointer">Push Notifications</Label>
                  </div>
                  <div className="flex items-center space-x-2">
                    <RadioGroupItem value="both" id="method-both" />
                    <Label htmlFor="method-both" className="cursor-pointer">Both</Label>
                  </div>
                </RadioGroup>
              </div>

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
                  You'll receive a notification when we find a booking price that's at least {priceAlertThreshold}% cheaper than your booked price.
                </p>
              </div>
            </CardContent>
            <CardFooter>
              <Button onClick={handleSaveNotificationSettings} disabled={isSaving}>
                {isSaving ? 'Saving...' : 'Save Notification Settings'}
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>
    </div>
  );
};

export default UserProfile;
