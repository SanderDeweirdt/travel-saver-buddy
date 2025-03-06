
import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';

const Index = () => {
  const navigate = useNavigate();
  const { user } = useAuth();

  const handleGetStarted = () => {
    if (user) {
      navigate('/dashboard');
    } else {
      navigate('/signup');
    }
  };

  const handleSignIn = () => {
    navigate('/signin');
  };

  return (
    <div className="min-h-screen flex flex-col">
      <main className="flex-1 flex flex-col items-center justify-center p-4 space-y-8">
        <div className="max-w-3xl w-full text-center space-y-6">
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold tracking-tight">
            Save Money on Your Hotel Bookings
          </h1>
          <p className="text-xl text-muted-foreground">
            Travel Buddy monitors your hotel bookings with free cancellation policies for price drops after you've booked. We'll notify you so you can rebook at the lower rate.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center pt-4">
            <Button size="lg" onClick={handleGetStarted}>
              Get Started
            </Button>
            {!user && (
              <Button size="lg" variant="outline" onClick={handleSignIn}>
                Sign In
              </Button>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Index;
