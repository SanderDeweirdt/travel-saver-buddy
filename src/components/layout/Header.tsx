
import React, { useState, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { Bell, User, Menu, X } from 'lucide-react';
import { Button } from '@/components/ui/button';

const Header = () => {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const location = useLocation();
  
  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };
    
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);
  
  useEffect(() => {
    setIsMobileMenuOpen(false);
  }, [location.pathname]);
  
  const isActive = (path: string) => location.pathname === path;
  
  return (
    <header 
      className={cn(
        "fixed top-0 left-0 right-0 z-50 transition-all duration-300 ease-in-out py-4 px-6 md:px-8",
        isScrolled ? "bg-white/90 backdrop-blur-md shadow-elevation-1" : "bg-transparent",
        isMobileMenuOpen && "bg-white/90 backdrop-blur-md"
      )}
    >
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <Link 
          to="/" 
          className="flex items-center space-x-2 relative z-50"
        >
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center">
            <span className="text-white font-semibold">TB</span>
          </div>
          <span className="font-semibold text-xl tracking-tight">TravelBuddy</span>
        </Link>
        
        <div className="hidden md:flex items-center space-x-8">
          <nav className="flex items-center space-x-6">
            <Link 
              to="/dashboard" 
              className={cn(
                "text-sm transition-colors hover:text-primary relative py-2", 
                isActive('/dashboard') ? "text-primary font-medium" : "text-foreground/80"
              )}
            >
              Dashboard
              {isActive('/dashboard') && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
              )}
            </Link>
            <Link 
              to="/bookings" 
              className={cn(
                "text-sm transition-colors hover:text-primary relative py-2", 
                isActive('/bookings') ? "text-primary font-medium" : "text-foreground/80"
              )}
            >
              My Bookings
              {isActive('/bookings') && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
              )}
            </Link>
            <Link 
              to="/add-booking" 
              className={cn(
                "text-sm transition-colors hover:text-primary relative py-2", 
                isActive('/add-booking') ? "text-primary font-medium" : "text-foreground/80"
              )}
            >
              Add Booking
              {isActive('/add-booking') && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
              )}
            </Link>
          </nav>
          
          <div className="flex items-center space-x-2">
            <Button variant="ghost" size="icon" className="rounded-full relative">
              <Bell size={18} />
              <span className="absolute top-0 right-0 w-2 h-2 bg-primary rounded-full" />
            </Button>
            
            <Link to="/profile">
              <Button variant={isActive('/profile') ? "default" : "ghost"} size="icon" className="rounded-full">
                <User size={18} />
              </Button>
            </Link>
          </div>
        </div>
        
        <button 
          className="md:hidden relative z-50" 
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        >
          {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
        
        {/* Mobile Menu */}
        <div 
          className={cn(
            "fixed inset-0 bg-white z-40 flex flex-col pt-24 px-6 transition-all duration-300 ease-in-out transform",
            isMobileMenuOpen ? "translate-x-0 opacity-100" : "translate-x-full opacity-0",
            "md:hidden"
          )}
        >
          <nav className="flex flex-col space-y-6 items-center">
            <Link 
              to="/dashboard" 
              className={cn(
                "text-lg w-full text-center py-3 rounded-lg transition-colors", 
                isActive('/dashboard') ? "bg-primary/10 text-primary font-medium" : "text-foreground"
              )}
            >
              Dashboard
            </Link>
            <Link 
              to="/bookings" 
              className={cn(
                "text-lg w-full text-center py-3 rounded-lg transition-colors", 
                isActive('/bookings') ? "bg-primary/10 text-primary font-medium" : "text-foreground"
              )}
            >
              My Bookings
            </Link>
            <Link 
              to="/add-booking" 
              className={cn(
                "text-lg w-full text-center py-3 rounded-lg transition-colors", 
                isActive('/add-booking') ? "bg-primary/10 text-primary font-medium" : "text-foreground"
              )}
            >
              Add Booking
            </Link>
            <Link 
              to="/profile" 
              className={cn(
                "text-lg w-full text-center py-3 rounded-lg transition-colors", 
                isActive('/profile') ? "bg-primary/10 text-primary font-medium" : "text-foreground"
              )}
            >
              Profile
            </Link>
          </nav>
        </div>
      </div>
    </header>
  );
};

export default Header;
