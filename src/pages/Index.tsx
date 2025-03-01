
import React, { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, TrendingDown, Shield, BarChart3 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/AuthContext';

const Index = () => {
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const [isScrolled, setIsScrolled] = React.useState(false);
  
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);
  
  const features = [
    {
      icon: <TrendingDown className="h-5 w-5" />,
      title: "Price Drop Alerts",
      description: "Get notified when hotel prices drop after booking so you can rebook at a lower rate."
    },
    {
      icon: <Shield className="h-5 w-5" />,
      title: "Free Cancellation Tracking",
      description: "We monitor your cancellation windows to ensure you can rebook without penalties."
    },
    {
      icon: <BarChart3 className="h-5 w-5" />,
      title: "Savings Dashboard",
      description: "Track all your savings in one place with our intuitive dashboard."
    }
  ];
  
  return (
    <div className="min-h-screen flex flex-col">
      <header 
        className={cn(
          "fixed top-0 left-0 right-0 z-50 transition-all duration-300 ease-in-out",
          isScrolled ? "bg-white/90 backdrop-blur-md shadow-elevation-1 py-4" : "bg-transparent py-6"
        )}
      >
        <div className="container max-w-7xl mx-auto px-4 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
              <span className="text-white font-semibold">TB</span>
            </div>
            <span className="font-semibold text-xl tracking-tight">TravelBuddy</span>
          </div>
          
          <div className="hidden md:flex space-x-6">
            {user ? (
              <>
                <Button 
                  variant="ghost" 
                  className="text-sm font-medium"
                  onClick={() => navigate('/dashboard')}
                >
                  Dashboard
                </Button>
                <Button 
                  variant="ghost" 
                  className="text-sm font-medium"
                  onClick={() => signOut()}
                >
                  Sign Out
                </Button>
              </>
            ) : (
              <>
                <Button 
                  variant="ghost" 
                  className="text-sm font-medium"
                  onClick={() => navigate('/signin')}
                >
                  Sign In
                </Button>
                <Button 
                  onClick={() => navigate('/signup')}
                  className="text-sm"
                >
                  Get Started
                </Button>
              </>
            )}
          </div>
          
          <Button 
            className="md:hidden"
            onClick={() => user ? navigate('/dashboard') : navigate('/signin')}
          >
            {user ? 'Dashboard' : 'Sign In'}
          </Button>
        </div>
      </header>
      
      <main className="flex-1">
        {/* Hero section */}
        <section className="pt-32 md:pt-40 pb-16 md:pb-24">
          <div className="container max-w-7xl mx-auto px-4">
            <div className="max-w-3xl mx-auto text-center">
              <h1 className="text-4xl md:text-5xl lg:text-6xl font-bold leading-tight tracking-tight animate-fade-in">
                Save money <span className="text-primary">after</span> you book
              </h1>
              <p className="mt-6 text-lg text-muted-foreground animate-fade-in animation-delay-200">
                TravelBuddy monitors your hotel bookings with free cancellation, 
                alerts you when prices drop, and helps you rebook to save money.
              </p>
              <div className="mt-10 flex flex-col sm:flex-row justify-center gap-4 animate-fade-in animation-delay-400">
                <Button 
                  size="lg" 
                  className="text-base px-8 h-12"
                  onClick={() => navigate('/signup')}
                >
                  Get Started
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Button>
                <Button 
                  variant="outline" 
                  size="lg" 
                  className="text-base px-8 h-12"
                  onClick={() => navigate('/dashboard')}
                >
                  View Demo
                </Button>
              </div>
            </div>
          </div>
        </section>
        
        {/* Features section */}
        <section className="py-16 md:py-24 bg-muted/30">
          <div className="container max-w-7xl mx-auto px-4">
            <div className="max-w-3xl mx-auto text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
                How TravelBuddy Works
              </h2>
              <p className="mt-4 text-muted-foreground text-lg">
                Our platform constantly monitors hotel prices after you book to help you save money.
              </p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {features.map((feature, index) => (
                <div 
                  key={index}
                  className="bg-white rounded-xl p-6 shadow-elevation-1 border border-border transition-all duration-300 hover:shadow-elevation-2"
                >
                  <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center mb-5">
                    <div className="text-primary">{feature.icon}</div>
                  </div>
                  <h3 className="text-xl font-semibold mb-3">{feature.title}</h3>
                  <p className="text-muted-foreground">{feature.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
        
        {/* How it works section */}
        <section className="py-16 md:py-24">
          <div className="container max-w-7xl mx-auto px-4">
            <div className="max-w-3xl mx-auto text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
                Post-Booking Price Optimization
              </h2>
              <p className="mt-4 text-muted-foreground text-lg">
                Unlike traditional travel search engines that only help before you book,
                TravelBuddy saves you money after you've already booked.
              </p>
            </div>
            
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
              <div className="order-2 lg:order-1">
                <div className="space-y-6">
                  <div className="flex items-start">
                    <div className="flex-shrink-0 flex h-8 w-8 rounded-full bg-primary/10 items-center justify-center mr-4">
                      <span className="text-primary font-medium">1</span>
                    </div>
                    <div>
                      <h3 className="text-lg font-medium mb-2">Forward your booking confirmation</h3>
                      <p className="text-muted-foreground">
                        Simply forward your hotel booking confirmation email to TravelBuddy or 
                        connect your Gmail account for automatic import.
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start">
                    <div className="flex-shrink-0 flex h-8 w-8 rounded-full bg-primary/10 items-center justify-center mr-4">
                      <span className="text-primary font-medium">2</span>
                    </div>
                    <div>
                      <h3 className="text-lg font-medium mb-2">We monitor price changes</h3>
                      <p className="text-muted-foreground">
                        Our system continually checks for price drops at your booked hotel before 
                        your free cancellation period expires.
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex items-start">
                    <div className="flex-shrink-0 flex h-8 w-8 rounded-full bg-primary/10 items-center justify-center mr-4">
                      <span className="text-primary font-medium">3</span>
                    </div>
                    <div>
                      <h3 className="text-lg font-medium mb-2">Get alerted & save money</h3>
                      <p className="text-muted-foreground">
                        When we find a lower price, we'll send you an alert with a link to rebook at 
                        the better rate. Cancel your original booking and pocket the difference.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="order-1 lg:order-2">
                <div className="bg-gray-100 rounded-xl overflow-hidden shadow-elevation-1 aspect-[4/3]">
                  <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-primary/5 to-primary/20">
                    <div className="bg-white/80 backdrop-blur-sm p-6 rounded-xl shadow-elevation-2 border border-white/20 w-4/5 max-w-md transform -rotate-1 transition-transform hover:rotate-0 duration-300">
                      <div className="flex items-start space-x-3">
                        <div className="bg-green-50 p-2 rounded-full">
                          <TrendingDown className="h-5 w-5 text-green-600" />
                        </div>
                        
                        <div className="flex-1">
                          <p className="text-xs font-medium text-green-600">Price Drop Alert</p>
                          
                          <h3 className="font-medium mt-1">Grand Hyatt New York</h3>
                          <p className="text-sm text-muted-foreground">New York, NY</p>
                          
                          <div className="mt-3 flex items-end justify-between">
                            <div>
                              <div className="flex items-baseline space-x-1.5">
                                <span className="text-sm line-through text-muted-foreground">
                                  $249
                                </span>
                                <span className="text-lg font-semibold text-green-600">
                                  $189
                                </span>
                              </div>
                              <p className="text-xs text-green-600 mt-0.5">
                                Save $60 (24%)
                              </p>
                            </div>
                            
                            <Button size="sm">
                              Rebook Now
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
        
        {/* CTA section */}
        <section className="py-16 md:py-24 bg-primary/5">
          <div className="container max-w-7xl mx-auto px-4">
            <div className="max-w-3xl mx-auto text-center">
              <h2 className="text-3xl md:text-4xl font-bold tracking-tight">
                Start saving on your hotel bookings
              </h2>
              <p className="mt-4 text-muted-foreground text-lg">
                Join thousands of travelers who are saving money after they book.
              </p>
              <Button 
                size="lg" 
                className="mt-8 text-base px-8 h-12"
                onClick={() => navigate('/signup')}
              >
                Get Started for Free
              </Button>
            </div>
          </div>
        </section>
      </main>
      
      <footer className="bg-muted/20 py-12 border-t border-border">
        <div className="container max-w-7xl mx-auto px-4">
          <div className="flex flex-col md:flex-row justify-between items-center">
            <div className="flex items-center space-x-2 mb-6 md:mb-0">
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
                <span className="text-white font-semibold">TB</span>
              </div>
              <span className="font-semibold text-xl tracking-tight">TravelBuddy</span>
            </div>
            
            <div className="flex flex-col md:flex-row space-y-6 md:space-y-0 md:space-x-12 items-center">
              <div className="flex space-x-6">
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground">About</a>
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground">Features</a>
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground">Pricing</a>
                <a href="#" className="text-sm text-muted-foreground hover:text-foreground">Contact</a>
              </div>
              
              <div className="flex space-x-4">
                <a href="#" className="text-muted-foreground hover:text-foreground">
                  <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M24 4.557c-.883.392-1.832.656-2.828.775 1.017-.609 1.798-1.574 2.165-2.724-.951.564-2.005.974-3.127 1.195-.897-.957-2.178-1.555-3.594-1.555-3.179 0-5.515 2.966-4.797 6.045-4.091-.205-7.719-2.165-10.148-5.144-1.29 2.213-.669 5.108 1.523 6.574-.806-.026-1.566-.247-2.229-.616-.054 2.281 1.581 4.415 3.949 4.89-.693.188-1.452.232-2.224.084.626 1.956 2.444 3.379 4.6 3.419-2.07 1.623-4.678 2.348-7.29 2.04 2.179 1.397 4.768 2.212 7.548 2.212 9.142 0 14.307-7.721 13.995-14.646.962-.695 1.797-1.562 2.457-2.549z" />
                  </svg>
                </a>
                <a href="#" className="text-muted-foreground hover:text-foreground">
                  <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
                  </svg>
                </a>
              </div>
            </div>
          </div>
          
          <div className="border-t border-border mt-8 pt-8 text-center">
            <p className="text-sm text-muted-foreground">
              © {new Date().getFullYear()} TravelBuddy. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Index;
